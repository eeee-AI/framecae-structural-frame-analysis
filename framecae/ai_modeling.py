"""AI 建模助手的服务端逻辑。

浏览器永远不会拿到 API Key。用户先确认材料、截面和题意中的缺失信息，
模型再提出节点、杆件、荷载和约束草案。服务端把已确认参数写入最终 JSON，
并调用既有输入校验；用户预览确认后才写入画布。
"""

from __future__ import annotations

import json
import math
import os
import re
from copy import deepcopy
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from framecae.core.material import Material
from framecae.core.section import Section
from framecae.io.payload import initial_payload, payload_to_model


_MODEL_KEYS = ("materials", "sections", "nodes", "elements", "loads", "constraints",
               "memberLoads", "temperatures", "assemblyDeviations")
_SYSTEM_PROMPT = """你是 FrameCAE 的结构建模助手。把用户的中文结构力学题目转换为
可供空间刚架有限元程序读取的建模草案。只返回 JSON。单位统一为 m、N、N·m。
节点坐标使用全局 x、y、z；平面题优先放在 x-z 平面（y=0）。
节点力采用 fx, fy, fz, mx, my, mz；向下荷载在 z 方向为负。
支座约束采用 ux,uy,uz,rx,ry,rz；固定端六个自由度均为 0，铰支端通常只约束
ux,uy,uz，除非题意另有说明。不要臆造材料和截面，也不要静默覆盖当前结构。
用户已确认材料、截面和补充问题的答案；严格采用这些信息。
非关键细节仍不明确时，写入 assumptions，不要静默伪造工程参数。
elements 的 material 和 section 固定填写 1；程序会将其映射到用户现有的第一项材料和截面。
"""
_BIGMODEL_OUTPUT_CONTRACT = """
输出必须严格遵循下面的 JSON 结构；不要输出 title、units、supports、node_i、node_j 或任何其他字段：
{
  "assistantMessage": "简短说明",
  "assumptions": ["需要用户核对的假设"],
  "recommendedGridStep": 0.5,
  "model": {
    "nodes": [{"id": 1, "x": 0, "y": 0, "z": 0}],
    "elements": [{"id": 1, "start": 1, "end": 2, "material": 1, "section": 1}],
    "loads": [{"node": 1, "fx": 0, "fy": 0, "fz": 0, "mx": 0, "my": 0, "mz": 0}],
    "constraints": [{"node": 1, "ux": 0, "uy": 0, "uz": 0, "rx": 0, "ry": 0, "rz": 0}]
  }
}
elements 的端点字段只能是 start 和 end；constraints 是唯一允许的支座字段名。所有数值必须是 JSON 数值而不是字符串。
没有荷载时输出空数组 []；自由度未约束时省略该自由度字段，不能写 null。只返回一个 JSON 对象。
"""
_BIGMODEL_QUESTION_PROMPT = """你是 FrameCAE 建模前的信息核对助手。根据用户题目，只找会影响
几何、杆件连接、支座或节点荷载建模的关键缺失信息；材料和截面由界面另行询问，不要在这里问。
本助手的草案目前只支持节点集中力和节点力矩，不支持把均布荷载写入草案；不得建议均布荷载作默认值。
自重由画布现有设置控制，不需要提问。若题目没给节点荷载，建议答案应为“暂不施加节点荷载”。
如果题目已经明确，就返回空 questions。若没有节点荷载或支座说明，应提出问题，并给出清楚标明为
暂用假设的建议答案供用户选择。每次最多问 4 个最关键的问题，问题要具体，建议答案要可直接
并入题目。只返回 JSON 对象，格式为 {"questions":[{"question":"...","default":"..."}]}。
不能返回节点、杆件或最终建模草案；不要使用 Markdown。
"""


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} 必须是数值。") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值。")
    return number


def _integer(value: Any, label: str) -> int:
    number = _number(value, label)
    if not number.is_integer() or number < 1:
        raise ValueError(f"{label} 必须是正整数。")
    return int(number)


def _as_rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{label} 必须是对象列表。")
    return value


def _request_inputs(prompt: Any, base_model: Any) -> tuple[str, dict[str, Any]]:
    prompt = str(prompt or "").strip()
    if len(prompt) < 4:
        raise ValueError("请至少输入一句结构题目描述。")
    if len(prompt) > 12000:
        raise ValueError("题目描述过长，请控制在 12000 个字符以内。")
    if not isinstance(base_model, dict):
        raise ValueError("当前模型数据无效。")
    for key, label in (("materials", "材料"), ("sections", "截面")):
        if key in base_model:
            _as_rows(base_model[key], label)
    return prompt, base_model


def _default_parameters(base_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    example = initial_payload()
    defaults = {}
    for kind, table in (("material", "materials"), ("section", "sections")):
        rows = base_model.get(table)
        candidate = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
        if candidate is not None:
            try:
                if kind == "material":
                    Material(_integer(candidate.get("id"), "材料号"), _number(candidate.get("e"), "E") * 1e9,
                             _number(candidate.get("nu"), "泊松比"), _number(candidate.get("density"), "密度"),
                             _number(candidate.get("alpha"), "线膨胀系数") * 1e-6)
                else:
                    Section(_integer(candidate.get("id"), "截面号"), _number(candidate.get("a"), "面积 A"),
                            _number(candidate.get("iy"), "Iy"), _number(candidate.get("iz"), "Iz"),
                            _number(candidate.get("j"), "扭转常数 J"), _number(candidate.get("d"), "特征尺寸 D"))
            except (TypeError, ValueError):
                candidate = None
        defaults[kind] = deepcopy(candidate if candidate is not None else example[table][0])
    return defaults


def _confirmed_base(base_model: dict[str, Any], confirmed: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(confirmed, dict):
        raise ValueError("请先回答材料、截面和题意补充问题，再生成建模草案。")
    defaults = _default_parameters(base_model)
    selected = {}
    fields = {"material": ("e", "nu", "alpha", "density"),
              "section": ("a", "iy", "iz", "j", "d")}
    for kind, label in (("material", "材料"), ("section", "截面")):
        choice = confirmed.get(kind)
        if not isinstance(choice, dict) or choice.get("mode") not in ("default", "custom"):
            raise ValueError(f"请确认是否使用默认{label}，或填写{label}参数。")
        if choice["mode"] == "default":
            selected[kind] = defaults[kind]
        else:
            values = choice.get("values")
            if not isinstance(values, dict):
                raise ValueError(f"请填写完整的{label}参数。")
            selected[kind] = {"id": defaults[kind]["id"], **{
                field: _number(values.get(field), f"{label} {field}") for field in fields[kind]
            }}

    answers = confirmed.get("answers", [])
    if not isinstance(answers, list) or len(answers) > 4:
        raise ValueError("题意补充答案格式无效。")
    answer_lines = []
    for index, item in enumerate(answers, start=1):
        if not isinstance(item, dict):
            raise ValueError("题意补充答案格式无效。")
        question, answer = str(item.get("question", "")).strip(), str(item.get("answer", "")).strip()
        if not question or not answer or len(question) > 300 or len(answer) > 500:
            raise ValueError(f"请回答第 {index} 个题意补充问题，答案不超过 500 字。")
        answer_lines.append(f"{question}：{answer}")

    prepared = deepcopy(base_model)
    material, section = selected["material"], selected["section"]
    material_id = _integer(material.get("id"), "材料号")
    section_id = _integer(section.get("id"), "截面号")
    e, nu, density, alpha = (_number(material.get(field), field) for field in ("e", "nu", "density", "alpha"))
    a, iy, iz, j, d = (_number(section.get(field), field) for field in ("a", "iy", "iz", "j", "d"))
    Material(material_id, e * 1e9, nu, density, alpha * 1e-6)
    Section(section_id, a, iy, iz, j, d)
    prepared["materials"] = [{"id": material_id, "e": e, "nu": nu, "density": density, "alpha": alpha},
                             *(base_model.get("materials") or [])[1:]]
    prepared["sections"] = [{"id": section_id, "a": a, "iy": iy, "iz": iz, "j": j, "d": d},
                            *(base_model.get("sections") or [])[1:]]
    return prepared, answer_lines


def review_model_request(prompt: Any, base_model: Any) -> dict[str, Any]:
    """Ask BigModel for missing structural facts; material and section are asked every time in UI."""
    prompt, base_model = _request_inputs(prompt, base_model)
    if os.environ.get("FRAMECAE_AI_PROVIDER", "bigmodel").strip().lower() != "bigmodel":
        raise ValueError("交互式参数核对目前仅支持 BigModel。")
    raw = _bigmodel_json(_BIGMODEL_QUESTION_PROMPT, prompt)
    questions = raw.get("questions")
    if not isinstance(questions, list) or len(questions) > 4:
        raise RuntimeError("BigModel 未返回有效的题意补充问题列表。")
    cleaned = []
    for item in questions:
        if not isinstance(item, dict):
            raise RuntimeError("BigModel 返回的题意问题格式无效。")
        question = str(item.get("question", "")).strip()
        default = str(item.get("default", "")).strip()
        if not question or len(question) > 300 or len(default) > 500:
            raise RuntimeError("BigModel 返回的题意问题缺少内容或过长。")
        cleaned.append({"question": question, "default": default})
    defaults = _default_parameters(base_model)
    return {
        "source": "bigmodel-glm", "questions": cleaned, "defaults": defaults,
        "defaultSources": {
            "material": "当前材料表" if base_model.get("materials") and defaults["material"] == base_model["materials"][0] else "软件示例参数",
            "section": "当前截面表" if base_model.get("sections") and defaults["section"] == base_model["sections"][0] else "软件示例参数",
        },
    }


def _canonicalize_bigmodel_draft(raw: dict[str, Any]) -> dict[str, Any]:
    """Map known GLM field aliases to the FrameCAE draft contract before validation.

    GLM's ``json_object`` mode guarantees valid JSON, but not a JSON Schema.  This
    adapter accepts the two aliases emitted by earlier GLM responses while keeping
    all numerical and finite-element validation in ``normalize_draft``.
    """
    result = deepcopy(raw)
    model = result.get("model", result)
    if not isinstance(model, dict):
        return result
    if "constraints" not in model and isinstance(model.get("supports"), list):
        model["constraints"] = model["supports"]
    if isinstance(model.get("elements"), list):
        for element in model["elements"]:
            if not isinstance(element, dict):
                continue
            if "start" not in element and "node_i" in element:
                element["start"] = element["node_i"]
            if "end" not in element and "node_j" in element:
                element["end"] = element["node_j"]
    if result.get("model") is not None:
        result["model"] = model
    return result


def normalize_draft(raw: dict[str, Any], base_model: dict[str, Any]) -> dict[str, Any]:
    """规范 AI 返回的草案，并用现有有限元输入层做一次完整校验。"""
    if not isinstance(raw, dict):
        raise ValueError("AI 返回的建模草案必须是对象。")
    model = raw.get("model", raw)
    if not isinstance(model, dict):
        raise ValueError("AI 返回中缺少 model 对象。")

    nodes, node_ids = [], set()
    for row in _as_rows(model.get("nodes", []), "节点"):
        node_id = _integer(row.get("id"), "节点号")
        if node_id in node_ids:
            raise ValueError(f"节点号 {node_id} 重复。")
        node_ids.add(node_id)
        nodes.append({"id": node_id, "x": _number(row.get("x"), f"N{node_id} x"),
                      "y": _number(row.get("y", 0), f"N{node_id} y"),
                      "z": _number(row.get("z"), f"N{node_id} z")})
    if len(nodes) < 2:
        raise ValueError("建模草案至少需要两个节点。")

    materials = deepcopy(base_model.get("materials", []))
    sections = deepcopy(base_model.get("sections", []))
    if not materials or not sections:
        raise ValueError("当前模型至少需要一项材料和一项截面，才能应用 AI 草案。")
    material_id, section_id = materials[0].get("id"), sections[0].get("id")

    elements, element_ids = [], set()
    for row in _as_rows(model.get("elements", []), "杆件"):
        element_id = _integer(row.get("id"), "杆件号")
        start, end = _integer(row.get("start"), f"E{element_id} 起点"), _integer(row.get("end"), f"E{element_id} 终点")
        if element_id in element_ids:
            raise ValueError(f"杆件号 {element_id} 重复。")
        if start not in node_ids or end not in node_ids:
            raise ValueError(f"E{element_id} 引用了不存在的节点。")
        if start == end:
            raise ValueError(f"E{element_id} 的两个端点不能是同一节点。")
        element_ids.add(element_id)
        elements.append({"id": element_id, "start": start, "end": end,
                         "material": material_id, "section": section_id})
    if not elements:
        raise ValueError("建模草案至少需要一根杆件。")

    loads = []
    for row in _as_rows(model.get("loads", []), "节点荷载"):
        node = _integer(row.get("node"), "荷载节点号")
        if node not in node_ids:
            raise ValueError(f"荷载引用的节点 N{node} 不存在。")
        loads.append({"node": node, **{field: _number(row.get(field, 0), f"N{node} {field}")
                                       for field in ("fx", "fy", "fz", "mx", "my", "mz")}})

    constraints = []
    valid_dofs = ("ux", "uy", "uz", "rx", "ry", "rz")
    for row in _as_rows(model.get("constraints", []), "边界条件"):
        node = _integer(row.get("node"), "约束节点号")
        if node not in node_ids:
            raise ValueError(f"约束引用的节点 N{node} 不存在。")
        item = {"node": node}
        for dof in valid_dofs:
            if dof in row and row[dof] not in (None, ""):
                item[dof] = _number(row[dof], f"N{node} {dof}")
        if len(item) == 1:
            raise ValueError(f"N{node} 没有指定任何约束自由度。")
        constraints.append(item)

    merged = deepcopy(base_model)
    merged.update({"materials": materials, "sections": sections, "nodes": nodes, "elements": elements,
                   "loads": loads, "constraints": constraints, "temperatures": [],
                   "memberLoads": [], "assemblyDeviations": []})
    # 复用程序真正用于计算的校验，检查截面引用、零长度杆件等。
    payload_to_model(merged)
    suggested = _number(raw.get("recommendedGridStep", _recommended_grid_step(nodes)), "推荐网格间距")
    if suggested <= 0:
        raise ValueError("推荐网格间距必须大于 0。")
    return {
        "assistantMessage": str(raw.get("assistantMessage", "已生成建模草案，请在画布中预览并确认。")),
        "assumptions": [str(item) for item in raw.get("assumptions", []) if str(item).strip()],
        "recommendedGridStep": suggested,
        "model": {key: merged[key] for key in _MODEL_KEYS},
        "summary": {"nodeCount": len(nodes), "elementCount": len(elements),
                    "loadCount": len(loads), "constraintCount": len(constraints)},
    }


def _recommended_grid_step(nodes: list[dict[str, float]]) -> float:
    span = max(max(row[axis] for row in nodes) - min(row[axis] for row in nodes)
               for axis in ("x", "y", "z"))
    return max(0.25, round(max(span / 8.0, 0.25) * 4) / 4)


def _openai_proposal(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置。")
    number = {"type": "number"}
    node = {"type": "object", "additionalProperties": False, "required": ["id", "x", "y", "z"],
            "properties": {"id": number, "x": number, "y": number, "z": number}}
    element = {"type": "object", "additionalProperties": False,
               "required": ["id", "start", "end", "material", "section"],
               "properties": {"id": number, "start": number, "end": number, "material": number, "section": number}}
    load = {"type": "object", "additionalProperties": False,
            "required": ["node", "fx", "fy", "fz", "mx", "my", "mz"],
            "properties": {key: number for key in ("node", "fx", "fy", "fz", "mx", "my", "mz")}}
    nullable_number = {"type": ["number", "null"]}
    constraint = {"type": "object", "additionalProperties": False,
                  "required": ["node", "ux", "uy", "uz", "rx", "ry", "rz"],
                  "properties": {"node": number, **{key: nullable_number for key in ("ux", "uy", "uz", "rx", "ry", "rz")}}}
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["assistantMessage", "assumptions", "recommendedGridStep", "model"],
        "properties": {
            "assistantMessage": {"type": "string"},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "recommendedGridStep": number,
            "model": {"type": "object", "additionalProperties": False,
                      "required": ["nodes", "elements", "loads", "constraints"],
                      "properties": {"nodes": {"type": "array", "items": node},
                                     "elements": {"type": "array", "items": element},
                                     "loads": {"type": "array", "items": load},
                                     "constraints": {"type": "array", "items": constraint}}},
        },
    }
    user_content: list[dict[str, Any]] = [{
        "type": "input_text",
        "text": prompt,
    }]
    request_body = {
        "model": os.environ.get("FRAMECAE_OPENAI_MODEL", "gpt-5-mini"),
        "store": False,
        "input": [{"role": "developer", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        "text": {"format": {"type": "json_schema", "name": "framecae_model_draft", "strict": True, "schema": schema}},
    }
    request = Request("https://api.openai.com/v1/responses", data=json.dumps(request_body).encode("utf-8"),
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API 请求失败（HTTP {error.code}）：{detail[:280]}") from error
    except URLError as error:
        raise RuntimeError(f"无法连接 OpenAI API：{error.reason}") from error
    output = body.get("output_text")
    if not output:
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    output = content.get("text")
                    break
    if not output:
        raise RuntimeError("OpenAI API 没有返回可读取的建模草案。")
    return _json_object_from_text(output, "OpenAI API")


def _json_object_from_text(value: Any, provider_name: str) -> dict[str, Any]:
    """Decode a provider response while tolerating thinking text and Markdown fences."""
    if not isinstance(value, str):
        raise RuntimeError(f"{provider_name} 没有返回可读取的 JSON 建模草案。")
    text = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError(f"{provider_name} 返回的建模草案不是有效 JSON。") from error
        try:
            result = json.loads(text[start:end + 1])
        except json.JSONDecodeError as nested_error:
            raise RuntimeError(f"{provider_name} 返回的建模草案不是有效 JSON。") from nested_error
    if not isinstance(result, dict):
        raise RuntimeError(f"{provider_name} 返回的建模草案必须是 JSON 对象。")
    return result


def _bigmodel_json(system_prompt: str, prompt: str, max_tokens: int = 4096) -> dict[str, Any]:
    """Request a JSON object from BigModel's Chat API without a local fallback."""
    api_key = os.environ.get("BIGMODEL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BIGMODEL_API_KEY 未配置。")

    user_content: list[dict[str, Any]] = [{
        "type": "text",
        "text": prompt,
    }]

    request_body = {
        "model": os.environ.get("FRAMECAE_GLM_MODEL", "glm-5.3-flash"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    endpoint = os.environ.get("FRAMECAE_BIGMODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/") + "/chat/completions"
    request = Request(endpoint, data=json.dumps(request_body).encode("utf-8"),
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=int(os.environ.get("FRAMECAE_AI_TIMEOUT", "150"))) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"BigModel GLM API 请求失败（HTTP {error.code}）：{detail[:280]}") from error
    except URLError as error:
        raise RuntimeError(f"无法连接 BigModel GLM API：{error.reason}") from error

    choices = body.get("choices") if isinstance(body, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    output = message.get("content") if isinstance(message, dict) else None
    if isinstance(output, list):
        output = "".join(part.get("text", "") for part in output if isinstance(part, dict))
    if not output and isinstance(choices, list) and choices and choices[0].get("finish_reason") == "length":
        raise RuntimeError("BigModel 在输出长度上限内未完成 JSON，请缩短题目或调高模型输出上限。")
    return _json_object_from_text(output, "BigModel GLM API")


def _bigmodel_proposal(prompt: str) -> dict[str, Any]:
    """Request a FrameCAE model draft from BigModel."""
    return _canonicalize_bigmodel_draft(_bigmodel_json(
        _SYSTEM_PROMPT + _BIGMODEL_OUTPUT_CONTRACT, prompt
    ))


def propose_model(prompt: Any, base_model: Any, confirmed_parameters: Any = None) -> dict[str, Any]:
    prompt, base_model = _request_inputs(prompt, base_model)
    base_model, answer_lines = _confirmed_base(base_model, confirmed_parameters)
    confirmed_text = "\n".join(answer_lines)
    material, section = base_model["materials"][0], base_model["sections"][0]
    prompt += ("\n用户已确认的材料参数（GPa、无量纲、10⁻⁶/K、kg/m³）：" + json.dumps(material, ensure_ascii=False)
               + "\n用户已确认的截面参数（m²、m⁴、m⁴、m⁴、m）：" + json.dumps(section, ensure_ascii=False))
    if confirmed_text:
        prompt += "\n用户对题意补充问题的回答：\n" + confirmed_text
    provider = os.environ.get("FRAMECAE_AI_PROVIDER", "bigmodel").strip().lower()
    if provider not in {"bigmodel", "openai"}:
        raise ValueError("FRAMECAE_AI_PROVIDER 仅支持 bigmodel 或 openai。")
    source = "bigmodel-glm" if provider == "bigmodel" else "openai"
    try:
        raw = _bigmodel_proposal(prompt) if provider == "bigmodel" else _openai_proposal(prompt)
    except RuntimeError as error:
        missing_key = "BIGMODEL_API_KEY 未配置。" if provider == "bigmodel" else "OPENAI_API_KEY 未配置。"
        if str(error) != missing_key:
            raise
        key_name = "BIGMODEL_API_KEY（GLM-5.3-Flash）" if provider == "bigmodel" else "OPENAI_API_KEY"
        raise RuntimeError(f"{key_name} 未配置；不会使用本地规则草案替代 AI 生成。") from error
    proposal = normalize_draft(raw, base_model)
    proposal["source"] = source
    proposal["provider"] = provider
    return proposal
