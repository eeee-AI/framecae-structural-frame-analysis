"""基于整体空间刚架内力的 Euler 弹性压杆稳定初步校核。"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

from framecae.core.model import Model
from framecae.postprocess.internal_force import sample_element_sections
from framecae.solver.static_solver import StaticResult


@dataclass(frozen=True)
class StabilityResult:
    """一根杆件的 Euler 稳定校核结果。

    本项目局部轴力 ``N>0`` 表示压力，``N<0`` 表示拉力。仅在沿杆
    存在压力时计算临界力与利用率；受拉杆的这些字段为 ``None``。
    """

    element_id: int
    status: str
    axial_force_design: float | None
    pcr_y: float | None
    pcr_z: float | None
    pcr: float | None
    utilization: float | None
    governing_axis: str | None
    slenderness_y: float | None
    slenderness_z: float | None
    mu_y: float
    mu_z: float


def check_model_stability(
    model: Model,
    result: StaticResult,
    effective_length_factors: dict[int, tuple[float, float]] | None = None,
) -> list[StabilityResult]:
    """逐杆读取整体梁内力并返回 Euler 压杆稳定结果。

    ``effective_length_factors`` 的每项为 ``(mu_y, mu_z)``。未给出的杆件
    使用 ``(1.0, 1.0)``，即课程中两端铰支的常用初步假定。
    """
    factors = effective_length_factors or {}
    results: list[StabilityResult] = []
    for element_id, element in sorted(model.elements.items()):
        mu_y, mu_z = factors.get(element_id, (1.0, 1.0))
        _validate_factor(mu_y, element_id, "μy")
        _validate_factor(mu_z, element_id, "μz")
        sampled = sample_element_sections(model, result, element_id)
        compression = [float(item.forces[0]) for item in sampled if item.forces[0] > 0.0]
        if not compression:
            results.append(StabilityResult(
                element_id=element_id, status="tension_or_zero", axial_force_design=None,
                pcr_y=None, pcr_z=None, pcr=None, utilization=None,
                governing_axis=None, slenderness_y=None, slenderness_z=None,
                mu_y=float(mu_y), mu_z=float(mu_z),
            ))
            continue

        section = element.section
        if section.area <= 0.0 or section.iy <= 0.0 or section.iz <= 0.0:
            raise ValueError(f"杆件 {element_id} 的 A、Iy、Iz 必须为正数，才能进行稳定校核。")
        if element.length <= 0.0 or element.material.elastic_modulus <= 0.0:
            raise ValueError(f"杆件 {element_id} 的长度和弹性模量必须为正数，才能进行稳定校核。")
        radius_y = sqrt(section.iy / section.area)
        radius_z = sqrt(section.iz / section.area)
        slenderness_y = float(mu_y) * element.length / radius_y
        slenderness_z = float(mu_z) * element.length / radius_z
        pcr_y = pi**2 * element.material.elastic_modulus * section.iy / (float(mu_y) * element.length) ** 2
        pcr_z = pi**2 * element.material.elastic_modulus * section.iz / (float(mu_z) * element.length) ** 2
        governing_axis = "y" if pcr_y <= pcr_z else "z"
        pcr = min(pcr_y, pcr_z)
        axial_force = max(compression)
        results.append(StabilityResult(
            element_id=element_id, status="compression", axial_force_design=axial_force,
            pcr_y=pcr_y, pcr_z=pcr_z, pcr=pcr,
            utilization=axial_force / pcr, governing_axis=governing_axis,
            slenderness_y=slenderness_y, slenderness_z=slenderness_z,
            mu_y=float(mu_y), mu_z=float(mu_z),
        ))
    return results


def _validate_factor(value: float, element_id: int, label: str) -> None:
    if not isinstance(value, (int, float)) or not 0.0 < float(value) < float("inf"):
        raise ValueError(f"杆件 {element_id} 的有效长度系数 {label} 必须为正数。")
