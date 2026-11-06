"""Convert a reviewed calibrated photo reconstruction into a FrameCAE draft."""

from __future__ import annotations

import math
from typing import Any

from framecae.ai_modeling import normalize_draft


def build_framecae_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Require metric scale and an explicit choice of photograph-supported rods."""
    if not isinstance(payload, dict):
        raise ValueError("图像建模草案请求无效。")
    reconstruction = payload.get("reconstruction")
    if not isinstance(reconstruction, dict) or reconstruction.get("unit") != "mm":
        raise ValueError("当前重建只有相对尺度。请填写两个标注点的实际毫米距离并重新重建，再应用到 FrameCAE。")
    if payload.get("confirmedMaterialSection") is not True:
        raise ValueError("请先确认本次使用当前模型中的材料和截面。")
    base_model = payload.get("baseModel")
    if not isinstance(base_model, dict) or not base_model.get("materials") or not base_model.get("sections"):
        raise ValueError("当前模型缺少材料或截面，请先在 FrameCAE 中填写。")

    points = reconstruction.get("points")
    candidates = payload.get("rodCandidates")
    selected_ids = payload.get("selectedRodIds")
    if not isinstance(points, list) or not 2 <= len(points) <= 20:
        raise ValueError("需要 2–20 个已重建节点。")
    if not isinstance(candidates, list) or not isinstance(selected_ids, list) or not selected_ids:
        raise ValueError("请先完成杆件识别，并至少人工确认一根杆件。")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("选择的杆件存在重复项。")

    node_ids: dict[str, int] = {}
    nodes: list[dict[str, float | int]] = []
    for index, point in enumerate(points, start=1):
        if not isinstance(point, dict) or not str(point.get("id", "")):
            raise ValueError("重建节点编号无效。")
        name = str(point["id"])
        if name in node_ids:
            raise ValueError("重建节点编号重复。")
        xyz = point.get("xyz")
        if not isinstance(xyz, list) or len(xyz) != 3:
            raise ValueError(f"节点 {name} 坐标无效。")
        try:
            coordinates = [float(value) / 1000.0 for value in xyz]
        except (TypeError, ValueError) as error:
            raise ValueError(f"节点 {name} 坐标无效。") from error
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError(f"节点 {name} 坐标无效。")
        node_ids[name] = index
        nodes.append({"id": index, "x": coordinates[0], "y": coordinates[1], "z": coordinates[2]})

    candidate_by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        a, b = str(candidate.get("a", "")), str(candidate.get("b", ""))
        if a not in node_ids or b not in node_ids or a == b:
            continue
        identifier = f"{a}:{b}"
        if candidate.get("id") == identifier:
            candidate_by_id[identifier] = candidate
    elements = []
    seen_pairs: set[frozenset[str]] = set()
    for identifier in selected_ids:
        if not isinstance(identifier, str) or identifier not in candidate_by_id:
            raise ValueError("所选杆件不在多视图识别结果中，请重新识别。")
        candidate = candidate_by_id[identifier]
        a, b = str(candidate["a"]), str(candidate["b"])
        pair = frozenset((a, b))
        if pair in seen_pairs:
            raise ValueError("选择的杆件存在重复连接。")
        seen_pairs.add(pair)
        elements.append({"id": len(elements) + 1, "start": node_ids[a], "end": node_ids[b]})

    spans = [max(node[axis] for node in nodes) - min(node[axis] for node in nodes)
             for axis in ("x", "y", "z")]
    rmse = reconstruction.get("overall_rmse_px")
    rmse_text = f"{float(rmse):.2f} px" if isinstance(rmse, (int, float)) and math.isfinite(rmse) else "未提供"
    raw = {
        "assistantMessage": "已将标定相机的多视图重建结果及人工勾选杆件转换为 FrameCAE 草案；请先预览并核对。",
        "assumptions": [
            "三维坐标来自相机标定、手动同名点、PnP 与 Bundle Adjustment，不是自然语言 AI 推测。",
            "坐标轴沿第一张照片的相机参考系，并非自动确定的工程全局方向。",
            "已知点间毫米距离已转换为 FrameCAE 的米；未从照片推断支座、荷载、材料、截面或连接刚度。",
            f"重投影 RMS：{rmse_text}；杆件由多视图线段证据提出，并由用户逐项选择。",
        ],
        "recommendedGridStep": max(0.05, max(spans) / 8.0),
        "model": {"nodes": nodes, "elements": elements, "loads": [], "constraints": []},
    }
    draft = normalize_draft(raw, base_model)
    draft.update({"source": "opencv-calibrated-manual-multiview", "status": "ok",
                  "metrics": {"calibrationMode": "measured", "viewCount": len(reconstruction.get("cameras", [])),
                              "reconstructionUnit": "mm", "modelUnit": "m",
                              "reprojectionRmsePx": rmse, "selectedRodCount": len(elements)}})
    return draft
