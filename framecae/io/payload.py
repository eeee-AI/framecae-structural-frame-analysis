"""浏览器输入数据与有限元模型之间的转换。"""

from __future__ import annotations

from typing import Any

import numpy as np

from examples.spatial_frame import build_space_frame
from framecae.core.member_load import PointMemberLoad, UniformMemberLoad
from framecae.core.material import Material
from framecae.core.model import DOF_LABELS, Model
from framecae.core.node import Node
from framecae.core.section import Section
from framecae.elements.frame3d import Frame3D
from framecae.local_analysis.critical_node import rank_critical_nodes, rank_critical_sections
from framecae.postprocess.element_force import recover_element_end_forces
from framecae.postprocess.displacement import build_element_curve, sample_curve
from framecae.postprocess.internal_force import evaluate_section, sample_element_sections
from framecae.postprocess.strength_check import (
    THEORY_LABELS, StrengthCheckOptions, check_model_strength,
)
from framecae.postprocess.stability_check import check_model_stability
from framecae.solver.static_solver import StaticSolver


# SciPy 共轭梯度仅保存稀疏矩阵；这里的上限用于避免浏览器请求长期占用。
# 它是资源控制，不是有限元收敛判据。
_GENERIC_CONVERGENCE_DEFAULT_MAX_DOFS = 150_000
_GENERIC_CONVERGENCE_HARD_MAX_DOFS = 300_000
from framecae.verification import run_global_verifications


def default_payload() -> dict[str, Any]:
    """返回默认空间刚架的可编辑 JSON 数据。"""
    return model_to_payload(build_space_frame())


def initial_payload() -> dict[str, Any]:
    """返回带示例材料和截面的空白画布，供手工或 AI 建模。"""
    example = default_payload()
    return {
        "materials": example["materials"],
        "sections": example["sections"],
        **{key: [] for key in (
            "nodes", "elements", "loads", "constraints", "memberLoads",
            "temperatures", "assemblyDeviations",
        )},
    }


def local_t_joint_demo_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def course_verification_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def model_to_payload(model: Model) -> dict[str, Any]:
    """把一个 Model 转为网页表格使用的数据格式。"""
    materials = {element.material.id: element.material for element in model.elements.values()}
    sections = {element.section.id: element.section for element in model.elements.values()}
    constraints: dict[int, dict[str, Any]] = {}
    for (node_id, dof), value in model.prescribed_dofs.items():
        constraints.setdefault(node_id, {"node": node_id})[DOF_LABELS[dof]] = value
    return {
        "materials": [
            {"id": item.id, "e": item.elastic_modulus / 1e9, "nu": item.poisson_ratio,
             "alpha": item.thermal_expansion * 1e6, "density": item.density}
            for item in materials.values()
        ],
        "sections": [
            {"id": item.id, "a": item.area, "iy": item.iy, "iz": item.iz, "j": item.torsion_constant, "d": item.characteristic_size}
            for item in sections.values()
        ],
        "nodes": [{"id": item.id, "x": item.x, "y": item.y, "z": item.z} for item in model.nodes.values()],
        "elements": [
            {"id": item.id, "start": item.start_node.id, "end": item.end_node.id, "material": item.material.id, "section": item.section.id}
            for item in model.elements.values()
        ],
        "loads": [
            {"node": node_id, "fx": values[0], "fy": values[1], "fz": values[2], "mx": values[3], "my": values[4], "mz": values[5]}
            for node_id, values in model.nodal_loads.items()
        ],
        "constraints": list(constraints.values()),
        "temperatures": [{"element": element_id, "deltaT": value} for element_id, value in model.element_temperature_changes.items()],
        "memberLoads": [
            {
                "element": element_id,
                "type": "uniform" if isinstance(load, UniformMemberLoad) else "point",
                "position": None if isinstance(load, UniformMemberLoad) else load.position,
                "qx": (load.input_components or load.local_components)[0],
                "qy": (load.input_components or load.local_components)[1],
                "qz": (load.input_components or load.local_components)[2],
                **({"coordinateSystem": load.coordinate_system, "unit": "N/m" if isinstance(load, UniformMemberLoad) else "N"}
                   if load.input_components is not None else {}),
            }
            for element_id, loads in model.member_loads.items()
            for load in loads
        ],
        "selfWeight": {
            "enabled": model.self_weight_enabled,
            "gx": float(model.gravity[0]), "gy": float(model.gravity[1]), "gz": float(model.gravity[2]),
        },
        "assemblyDeviations": [
            {"element": element_id, "deltaLength": delta_length}
            for element_id, delta_length in sorted(model.element_length_deviations.items())
            if delta_length != 0.0
        ],
    }


def solve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """将浏览器表格数据求解为可供三维图和结果表使用的结果数据。"""
    model = payload_to_model(payload)
    result = StaticSolver().solve(model)
    end_forces = recover_element_end_forces(model, result)
    node_results = []
    maximum_node, maximum_displacement = None, -1.0
    total_reaction = np.zeros(6)
    for node_id in sorted(model.nodes):
        node = model.nodes[node_id]
        displacement = result.node_displacement(model, node_id)
        magnitude = float(np.linalg.norm(displacement[:3]))
        if magnitude > maximum_displacement:
            maximum_node, maximum_displacement = node_id, magnitude
        total_reaction += result.reactions[node.dof_indices]
        node_results.append({
            "id": node_id,
            "coordinate": node.coordinates.tolist(),
            "displacement": displacement.tolist(),
            "magnitude": magnitude,
            "reaction": result.reactions[node.dof_indices].tolist(),
        })
    element_results = []
    deformation_peak = {"magnitude": -1.0, "element": None, "position": None}
    for element_id, element in model.elements.items():
        forces = end_forces[element_id]
        stations = sample_element_sections(model, result, element_id)
        maximum_axial = max(abs(item.forces[0]) for item in stations)
        maximum_bending = max(
            float(np.hypot(item.forces[4], item.forces[5])) for item in stations
        )
        maximum_nominal = max(abs(item.nominal_stress) for item in stations)
        curve = build_element_curve(model, result, element_id)
        if curve["peak"]["magnitude"] > deformation_peak["magnitude"]:
            deformation_peak = {**curve["peak"], "element": element_id}
        element_results.append({
            "id": element_id,
            "start": element.start_node.id,
            "end": element.end_node.id,
            # 局部坐标轴在全局坐标下的方向余弦；浏览器 05 内力图据此绘制
            # My、Mz 的两个正交图面和遵循右手定则的扭矩方向。
            "localAxes": element.rotation.tolist(),
            "deformationCurve": curve,
            "deformation": sample_curve(curve),
            "startForce": forces.start.tolist(),
            "endForce": forces.end.tolist(),
            "maxAxialForce": maximum_axial,
            "maxBendingMoment": maximum_bending,
            "maxNominalStress": maximum_nominal,
            "stations": [
                {"position": item.position, "forces": item.forces.tolist(), "nominalStress": item.nominal_stress}
                for item in stations
            ],
        })
    critical_nodes = rank_critical_nodes(model, result)
    critical_sections = rank_critical_sections(model, result)
    assembly_summary = []
    for element_id, delta_length in sorted(model.element_length_deviations.items()):
        if delta_length == 0.0:
            continue
        element = model.elements[element_id]
        assembly_summary.append({
            "element": element_id,
            "deltaLength": delta_length,
            "installationStrain": delta_length / element.length,
            "initialAxialForce": -model.local_assembly_equivalent_load(element_id)[0],
            "startAxialForce": float(end_forces[element_id].start[0]),
            "endAxialForce": float(end_forces[element_id].end[0]),
        })
    return {
        "solvedModel": model_to_payload(model),
        "nodes": node_results,
        "elements": element_results,
        "criticalNodes": [
            {
                "id": item.node_id,
                "nominalStress": item.nominal_stress,
                "elements": list(item.connected_elements),
            }
            for item in critical_nodes
        ],
        "criticalSections": [
            {
                "element": item.element_id,
                "position": item.position,
                "nominalStress": item.nominal_stress,
            }
            for item in critical_sections[:10]
        ],
        "summary": {
            "nodeCount": len(model.nodes),
            "elementCount": len(model.elements),
            "maxNode": maximum_node,
            "maxDisplacement": maximum_displacement,
            "deformation": {
                "method": "Euler-Bernoulli piecewise polynomial: Hermite + member-load particular solution",
                "curvePeak": deformation_peak,
                "peakMethod": "floating-point stationary points of squared displacement norm and interval endpoints",
                "renderToleranceCssPixels": 0.5,
                "assumptions": "线弹性、小位移、等截面空间梁；不计横向剪切变形；共节点转角兼容。",
            },
            "totalReaction": total_reaction.tolist(),
            "selfWeight": {
                "enabled": model.self_weight_enabled,
                "gravity": model.gravity.tolist(),
                "totalWeight": model.total_self_weight().tolist(),
                "totalMass": float(sum(
                    element.material.density * element.section.area * element.length
                    for element in model.elements.values()
                )),
            },
            "assembly": assembly_summary,
        },
    }


def strength_check_payload(request: dict[str, Any]) -> dict[str, Any]:
    """对整体空间刚架执行圆管危险截面四大强度理论校核。"""
    if not isinstance(request, dict):
        raise ValueError("强度校核请求必须是对象。")
    model = payload_to_model(request.get("model"))
    settings = request.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("强度校核参数必须是对象。")
    options = StrengthCheckOptions(
        yield_strength=_setting_number_or_default(settings, "yieldStrength", 355.0e6),
        tensile_strength=_setting_number_or_default(settings, "tensileStrength", 355.0e6),
        compressive_strength=_setting_number_or_default(settings, "compressiveStrength", 355.0e6),
        extremum_tolerance=_setting_number_or_default(settings, "extremumTolerance", 1e-6),
        circumferential_points=_setting_integer_or_default(settings, "circumferentialPoints", 32),
        include_average_transverse_shear=bool(settings.get("includeAverageTransverseShear", True)),
    )
    checked = check_model_strength(model, StaticSolver().solve(model), options)

    def serialize(point) -> dict[str, Any]:
        theory = max(THEORY_LABELS, key=lambda item: point.utilizations[item])
        element = model.elements[point.element_id]
        return {
            "element": point.element_id,
            "position": point.position,
            "elementLength": element.length,
            "angleDegrees": float(np.degrees(point.angle)),
            "globalPosition": point.global_position.tolist(),
            "forces": point.forces.tolist(),
            "stressTensor": point.stress_tensor.tolist(),
            "principalStresses": point.principal_stresses.tolist(),
            "equivalentStresses": point.equivalents,
            "utilizations": point.utilizations,
            "governingTheory": theory,
        }

    return {
        "theories": {
            theory: {"label": THEORY_LABELS[theory], "critical": serialize(point)}
            for theory, point in checked["critical"].items()
        },
        "memberUtilizations": [
            {"element": element_id, **values}
            for element_id, values in sorted(checked["member_maxima"].items())
        ],
        "pointCount": checked["point_count"],
        "method": checked["method"],
        "extremumTolerance": checked["extremumTolerance"],
        "searchDiagnostics": checked["searchDiagnostics"],
        "skippedElements": checked["skipped_elements"],
        "assumptions": [
            "这是整体梁模型的名义截面强度校核，不包含焊缝、孔洞、相贯线等局部应力集中。",
            "以 D 定义圆形外缘，通过驻点方程求周向极值，沿杆分段求控制位置；扭转剪应力按 Saint-Venant 圆管解恢复。",
            "正式圆管设计应输入彼此一致的 A、Iy、Iz、J、D；等效截面仅适合课程级比较。",
            "若勾选横向剪力，Vy、Vz 按平均剪应力 V/A 计入，适合课程级工程估算。",
            "延性钢材通常以 von Mises 为主判据，Tresca 作为保守对照；Rankine 更适合脆性材料。",
        ],
    }


def stability_check_payload(request: dict[str, Any]) -> dict[str, Any]:
    """按整体刚架受压内力执行 Euler 弹性压杆稳定初步校核。"""
    if not isinstance(request, dict):
        raise ValueError("稳定校核请求必须是对象。")
    model = payload_to_model(request.get("model"))
    settings = request.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("稳定校核参数必须是对象。")
    default_mu_y = _positive_setting(settings, "defaultMuY", 1.0, "默认 μy")
    default_mu_z = _positive_setting(settings, "defaultMuZ", 1.0, "默认 μz")
    factors = {element_id: (default_mu_y, default_mu_z) for element_id in model.elements}
    seen: set[int] = set()
    for row_number, row in enumerate(_list(settings, "members"), start=1):
        element_id = _integer(row, "element", f"稳定参数表第 {row_number} 行杆件号")
        if element_id not in model.elements:
            raise ValueError(f"稳定参数表第 {row_number} 行引用的杆件 {element_id} 不存在。")
        if element_id in seen:
            raise ValueError(f"稳定参数表中杆件 {element_id} 重复。")
        seen.add(element_id)
        factors[element_id] = (
            _positive_setting(row, "muY", default_mu_y, f"杆件 {element_id} 的 μy"),
            _positive_setting(row, "muZ", default_mu_z, f"杆件 {element_id} 的 μz"),
        )
    checked = check_model_stability(model, StaticSolver().solve(model), factors)

    def serialize(item: Any) -> dict[str, Any]:
        return {
            "element": item.element_id, "status": item.status,
            "axialForce": item.axial_force_design,
            "pcrY": item.pcr_y, "pcrZ": item.pcr_z, "pcr": item.pcr,
            "utilization": item.utilization, "governingAxis": item.governing_axis,
            "slendernessY": item.slenderness_y, "slendernessZ": item.slenderness_z,
            "muY": item.mu_y, "muZ": item.mu_z,
        }

    compressed = [item for item in checked if item.status == "compression"]
    critical = max(compressed, key=lambda item: item.utilization or -1.0, default=None)
    pass_count = sum((item.utilization or 0.0) <= 0.80 for item in compressed)
    warning_count = sum(0.80 < (item.utilization or 0.0) <= 1.0 for item in compressed)
    fail_count = sum((item.utilization or 0.0) > 1.0 for item in compressed)
    return {
        "members": [serialize(item) for item in checked],
        "critical": None if critical is None else serialize(critical),
        "summary": {
            "checkedMemberCount": len(checked), "compressionMemberCount": len(compressed),
            "passCount": pass_count, "warningCount": warning_count, "failCount": fail_count,
        },
        "assumptions": [
            "本结果为基于整体梁内力的 Euler 弹性压杆稳定初步校核，仅对沿杆存在压力的杆件计算。",
            "未包含规范稳定系数、初始几何缺陷、残余应力、局部屈曲、连接半刚性、侧向支撑、几何非线性及二阶效应。",
            "实际工程设计应按适用规范并结合构件端部约束、支撑和非线性屈曲分析进一步校核。",
        ],
    }




def solve_local_t_joint_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def solve_generic_tubular_node_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def solve_generic_tubular_node_convergence_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def solve_local_t_joint_convergence_payload(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")














def suggest_t_joint_settings(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")


def suggest_generic_tubular_node_settings(*args,**kwargs):
    raise ValueError("本发行版只支持03自编截面内力驱动接口。")






def payload_to_model(payload: dict[str, Any]) -> Model:
    """读取网页数据并进行完整的引用、数值和单位检查。"""
    if not isinstance(payload, dict):
        raise ValueError("输入数据必须是对象。")
    materials: dict[int, Material] = {}
    for row_number, row in enumerate(_list(payload, "materials"), start=1):
        material_id = _integer(row, "id", f"材料表第 {row_number} 行")
        if material_id in materials:
            raise ValueError(f"材料号 {material_id} 重复。")
        materials[material_id] = Material(
            material_id,
            _number(row, "e", f"材料表第 {row_number} 行 E") * 1e9,
            _number(row, "nu", f"材料表第 {row_number} 行泊松比"),
            density=_number_or_default(row, "density", 7850.0, f"材料表第 {row_number} 行密度"),
            thermal_expansion=_number(row, "alpha", f"材料表第 {row_number} 行热膨胀系数") * 1e-6,
        )
    sections: dict[int, Section] = {}
    for row_number, row in enumerate(_list(payload, "sections"), start=1):
        section_id = _integer(row, "id", f"截面表第 {row_number} 行")
        if section_id in sections:
            raise ValueError(f"截面号 {section_id} 重复。")
        sections[section_id] = Section(
            section_id,
            _number(row, "a", f"截面表第 {row_number} 行 A"),
            _number(row, "iy", f"截面表第 {row_number} 行 Iy"),
            _number(row, "iz", f"截面表第 {row_number} 行 Iz"),
            _number(row, "j", f"截面表第 {row_number} 行 J"),
            _number(row, "d", f"截面表第 {row_number} 行 D"),
        )
    if not materials or not sections:
        raise ValueError("请至少输入一种材料和一种截面。")

    model = Model()
    for row_number, row in enumerate(_list(payload, "nodes"), start=1):
        model.add_node(Node(
            _integer(row, "id", f"节点表第 {row_number} 行"),
            _number(row, "x", f"节点表第 {row_number} 行 x"),
            _number(row, "y", f"节点表第 {row_number} 行 y"),
            _number(row, "z", f"节点表第 {row_number} 行 z"),
        ))
    for row_number, row in enumerate(_list(payload, "elements"), start=1):
        element_id = _integer(row, "id", f"杆件表第 {row_number} 行")
        start_id = _integer(row, "start", f"杆件表第 {row_number} 行起点节点")
        end_id = _integer(row, "end", f"杆件表第 {row_number} 行终点节点")
        material_id = _integer(row, "material", f"杆件表第 {row_number} 行材料号")
        section_id = _integer(row, "section", f"杆件表第 {row_number} 行截面号")
        if start_id not in model.nodes or end_id not in model.nodes:
            raise ValueError(f"杆件 {element_id} 引用了不存在的节点。")
        if material_id not in materials or section_id not in sections:
            raise ValueError(f"杆件 {element_id} 引用了不存在的材料号或截面号。")
        model.add_element(Frame3D(element_id, model.nodes[start_id], model.nodes[end_id], materials[material_id], sections[section_id]))
    for row_number, row in enumerate(_list(payload, "loads"), start=1):
        model.add_nodal_load(
            _integer(row, "node", f"荷载表第 {row_number} 行节点号"),
            [_number(row, field, f"荷载表第 {row_number} 行 {field}") for field in ("fx", "fy", "fz", "mx", "my", "mz")],
        )
    for row_number, row in enumerate(_list(payload, "constraints"), start=1):
        node_id = _integer(row, "node", f"约束表第 {row_number} 行节点号")
        for dof, field in enumerate(DOF_LABELS):
            if field in row and row[field] not in (None, ""):
                model.prescribe_dof(node_id, dof, _number(row, field, f"约束表第 {row_number} 行 {field}"))
    for row_number, row in enumerate(_list(payload, "temperatures"), start=1):
        model.set_element_temperature_change(
            _integer(row, "element", f"温差表第 {row_number} 行杆件号"),
            _number(row, "deltaT", f"温差表第 {row_number} 行温差"),
        )
    for row_number, row in enumerate(_list(payload, "memberLoads"), start=1):
        element_id = _integer(row, "element", f"杆件荷载表第 {row_number} 行杆件号")
        components = [_number(row, field, f"杆件荷载表第 {row_number} 行 {field}") for field in ("qx", "qy", "qz")]
        load_type = str(row.get("type", "")).lower()
        coordinate_system = str(row.get("coordinateSystem") or "local").lower()
        if coordinate_system not in ("local", "global"):
            raise ValueError(f"杆件荷载表第 {row_number} 行坐标系必须为 local 或 global。")
        expected_unit = "N/m" if load_type == "uniform" else "N"
        if row.get("unit") not in (None, "", expected_unit):
            raise ValueError(f"杆件荷载表第 {row_number} 行单位必须为 {expected_unit}。")
        original_components = tuple(components)
        if coordinate_system == "global":
            if element_id not in model.elements:
                raise ValueError(f"杆件 {element_id} 不存在。")
            components = model.elements[element_id].rotation @ components
        if load_type == "uniform":
            model.add_uniform_member_load(element_id, components)
        elif load_type == "point":
            model.add_point_member_load(
                element_id,
                _number(row, "position", f"杆件荷载表第 {row_number} 行作用位置"),
                components,
            )
        else:
            raise ValueError(f"杆件荷载表第 {row_number} 行类型必须为 uniform 或 point。")
        if "coordinateSystem" in row or "unit" in row:
            from dataclasses import replace
            model.member_loads[element_id][-1] = replace(
                model.member_loads[element_id][-1], coordinate_system=coordinate_system,
                input_components=original_components)
    self_weight = payload.get("selfWeight", {})
    if self_weight not in (None, ""):
        if not isinstance(self_weight, dict):
            raise ValueError("selfWeight 必须是对象。")
        model.set_self_weight(
            bool(self_weight.get("enabled", False)),
            [_number_or_default(self_weight, axis, default, f"自重重力 {axis}")
             for axis, default in (("gx", 0.0), ("gy", 0.0), ("gz", -9.81))],
        )
    for row_number, row in enumerate(_list(payload, "assemblyDeviations"), start=1):
        model.set_element_length_deviation(
            _integer(row, "element", f"装配偏差表第 {row_number} 行杆件号"),
            _number(row, "deltaLength", f"装配偏差表第 {row_number} 行长度偏差"),
        )
    if not model.nodes or not model.elements:
        raise ValueError("模型至少需要一个节点和一个杆件。")
    return model


def _list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} 必须是列表。")
    if not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{key} 中每一行必须是对象。")
    return value


def _number(row: dict[str, Any], key: str, label: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label} 必须是数字。") from error


def _number_or_default(row: dict[str, Any], key: str, default: float, label: str) -> float:
    value = row.get(key, default)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} 必须是数字。") from error


def _integer(row: dict[str, Any], key: str, label: str) -> int:
    value = _number(row, key, label)
    if not value.is_integer():
        raise ValueError(f"{label} 必须是整数。")
    return int(value)


def _setting_number(settings: dict[str, Any], key: str, label: str) -> float:
    try:
        return float(settings[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label} 必须是数字。") from error


def _setting_integer(settings: dict[str, Any], key: str, label: str) -> int:
    value = _setting_number(settings, key, label)
    if not value.is_integer():
        raise ValueError(f"{label} 必须是整数。")
    return int(value)


def _setting_number_or_default(settings: dict[str, Any], key: str, default: float) -> float:
    """读取可选数值；空值沿用课程算例的默认材料强度。"""
    value = settings.get(key, default)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key} 必须是数字。") from error


def _positive_setting(settings: dict[str, Any], key: str, default: float, label: str) -> float:
    """读取正数设置，适用于有效长度系数等物理参数。"""
    value = _setting_number_or_default(settings, key, default)
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} 必须是正数。")
    return value


def _setting_integer_or_default(settings: dict[str, Any], key: str, default: int) -> int:
    value = _setting_number_or_default(settings, key, float(default))
    if not value.is_integer():
        raise ValueError(f"{key} 必须是整数。")
    return int(value)


def _outgoing_direction_at_node(element: Frame3D, node_id: int) -> np.ndarray:
    if element.start_node.id == node_id:
        vector = element.end_node.coordinates - element.start_node.coordinates
    else:
        vector = element.start_node.coordinates - element.end_node.coordinates
    return vector / np.linalg.norm(vector)


def _same_circular_section(sections: list[Section]) -> bool:
    """仅在外径和面积均一致且可反算空心圆管时自动填写几何参数。"""
    reference = sections[0]
    if reference.characteristic_size <= 0.0 or reference.area <= 0.0:
        return False
    return all(
        np.isclose(item.characteristic_size, reference.characteristic_size)
        and np.isclose(item.area, reference.area)
        and item.area <= np.pi * (item.characteristic_size / 2.0) ** 2
        for item in sections
    )
