"""Fixed-volume sizing iterations for the existing three-dimensional frame solver.

Every trial replaces each member's complete, geometrically similar section,
then reassembles and resolves the frame.  The stress measure is a conservative
nominal beam-section von Mises proxy; local joints and design-code interaction
rules are outside this sizing calculation.
"""

from __future__ import annotations

from math import pi, sqrt

import numpy as np

from framecae.core.section import Section
from framecae.io.payload import model_to_payload, payload_to_model
from framecae.postprocess.internal_force import sample_element_sections
from framecae.solver.static_solver import StaticSolver


def _positive(settings: dict, key: str, default: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必须是正的有限数。") from exc
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{key} 必须是正的有限数。")
    return value


def _project(weights: np.ndarray, lower: np.ndarray, upper: np.ndarray,
             lengths: np.ndarray, volume: float) -> np.ndarray:
    """Bounded proportional allocation with sum(A_i L_i) = volume."""
    if float(lower @ lengths) > volume * (1 + 1e-10):
        raise ValueError("最小截面面积超过固定材料体积。")
    if float(upper @ lengths) < volume * (1 - 1e-10):
        raise ValueError("截面增幅限制不足以容纳固定材料体积。")
    left, right = 0.0, max(float(np.max(upper / weights)), 1.0)
    for _ in range(100):
        middle = (left + right) / 2
        trial = np.clip(middle * weights, lower, upper)
        if float(trial @ lengths) < volume:
            left = middle
        else:
            right = middle
    return np.clip(right * weights, lower, upper)


def _stress_utilization(element, stations, allowable: float) -> tuple[float, float, float, float]:
    """Return (utilization, equivalent stress, max |N|, max bending moment)."""
    section = element.section
    radius = section.characteristic_size / 2
    maximum_equivalent = maximum_axial = maximum_bending = 0.0
    for station in stations:
        axial, shear_y, shear_z, torsion, moment_y, moment_z = station.forces
        # The circular outer-fibre proxy maximises combined biaxial bending.
        normal = abs(axial) / section.area + radius * sqrt(
            (moment_y / section.iy) ** 2 + (moment_z / section.iz) ** 2)
        # Sum the transverse-shear and torsion magnitudes conservatively.
        shear = float(np.hypot(shear_y, shear_z)) / section.area
        shear += abs(torsion) * radius / section.torsion_constant
        equivalent = sqrt(normal**2 + 3 * shear**2)
        maximum_equivalent = max(maximum_equivalent, equivalent)
        maximum_axial = max(maximum_axial, abs(axial))
        maximum_bending = max(maximum_bending, float(np.hypot(moment_y, moment_z)))
    return maximum_equivalent / allowable, maximum_equivalent, maximum_axial, maximum_bending


def optimize_frame_full_stress(request: dict) -> dict:
    """Run a fixed-volume, nominal fully stressed sizing study on a space frame."""
    if not isinstance(request, dict):
        raise ValueError("请求必须是对象。")
    model = payload_to_model(request.get("model"))
    settings = request.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings 必须是对象。")
    allowable = _positive(settings, "allowableStress", 235e6)
    minimum_fraction = _positive(settings, "minAreaFraction", 0.01)
    move_limit = _positive(settings, "moveLimit", 0.5)
    damping = 0.5
    tolerance = _positive(settings, "tolerance", 0.001)
    effective_length = _positive(settings, "effectiveLengthFactor", 1.0)
    if minimum_fraction >= 1 or move_limit >= 1:
        raise ValueError("最小面积比例和单轮变化比例必须小于 1。")
    try:
        max_iterations = int(settings.get("maxIterations", 30))
    except (TypeError, ValueError) as exc:
        raise ValueError("maxIterations 必须是整数。") from exc
    if not 1 <= max_iterations <= 100:
        raise ValueError("maxIterations 必须在 1 到 100 之间。")
    ids = sorted(model.elements)
    originals = [model.elements[element_id].section for element_id in ids]
    initial_areas = np.array([section.area for section in originals], dtype=float)
    lengths = np.array([model.elements[element_id].length for element_id in ids], dtype=float)
    volume = float(initial_areas @ lengths)
    areas = initial_areas.copy()
    section_id_start = max(section.id for section in originals) + 1
    solver = StaticSolver(method="scipy" if 6 * len(model.nodes) > 2000 else "ldlt")
    history: list[dict] = []
    converged = False
    for iteration in range(max_iterations + 1):
        for index, element_id in enumerate(ids):
            original = originals[index]
            scale = float(areas[index] / initial_areas[index])
            model.elements[element_id].section = Section(
                section_id_start + index, float(areas[index]),
                original.iy * scale**2, original.iz * scale**2,
                original.torsion_constant * scale**2,
                original.characteristic_size * sqrt(scale),
            )
        try:
            result = solver.solve(model)
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise ValueError(f"第 {iteration} 轮刚架重分析失败：{exc}") from exc
        data: list[dict] = []
        for index, element_id in enumerate(ids):
            element = model.elements[element_id]
            stations = sample_element_sections(model, result, element_id)
            strength, stress, max_axial, max_bending = _stress_utilization(
                element, stations, allowable)
            maximum_compression = max((float(station.forces[0]) for station in stations), default=0.0)
            maximum_compression = max(maximum_compression, 0.0)
            critical_y = pi**2 * element.material.elastic_modulus * element.section.iy / (effective_length * element.length)**2
            critical_z = pi**2 * element.material.elastic_modulus * element.section.iz / (effective_length * element.length)**2
            stability = maximum_compression / min(critical_y, critical_z)
            data.append({
                "id": element_id, "length": float(lengths[index]), "area": float(areas[index]),
                "areaRatio": float(areas[index] / initial_areas[index]),
                "maxAxialForce": max_axial, "maxBendingMoment": max_bending,
                "equivalentStress": stress,
                "strengthUtilization": strength, "stabilityUtilization": stability,
                "utilization": max(strength, stability),
                "governing": "稳定" if stability > strength else "强度",
            })
        data.sort(key=lambda row: (-row["utilization"], row["id"]))
        for rank, row in enumerate(data, 1):
            row["rank"] = rank
        max_displacement = max(float(np.linalg.norm(result.node_displacement(model, node_id)[:3]))
                               for node_id in model.nodes)
        history.append({
            "iteration": iteration, "volume": float(areas @ lengths),
            "maxUtilization": max(row["utilization"] for row in data),
            "maxStrengthUtilization": max(row["strengthUtilization"] for row in data),
            "maxStabilityUtilization": max(row["stabilityUtilization"] for row in data),
            "maxDisplacement": max_displacement, "members": data,
        })
        if iteration == max_iterations:
            break
        utilizations = np.array([next(row["utilization"] for row in data if row["id"] == element_id)
                                 for element_id in ids])
        weights = areas * np.sqrt(np.maximum(utilizations, 1e-9))
        lower = np.maximum(initial_areas * minimum_fraction, areas * (1 - move_limit))
        upper = areas * (1 + move_limit)
        target = _project(weights, lower, upper, lengths, volume)
        updated = (1 - damping) * areas + damping * target
        change = float(np.max(np.abs(updated / areas - 1)))
        if change < tolerance:
            converged = True
            break
        areas = updated

    final = history[-1]
    return {
        "method": "space_frame_fixed_volume_full_stress_sizing",
        "initialVolume": volume, "finalVolume": final["volume"],
        "converged": converged, "iterations": len(history) - 1,
        "history": history,
        "optimizedModel": model_to_payload(model),
        "candidateRemovalIds": [row["id"] for row in final["members"]
                                if row["areaRatio"] <= max(minimum_fraction * 1.01, 0.05)],
        "notes": [
            "本结果由三维空间刚架单元重分析得到，计入轴力、双向弯矩、扭矩及平均剪力。",
            "截面按几何相似缩放；强度是名义梁截面估算，稳定采用指定有效长度系数的 Euler 初步校核。",
            "极小面积构件未实际删除；焊缝、节点、位移限值及删杆后稳定性须独立校核。",
        ],
    }
