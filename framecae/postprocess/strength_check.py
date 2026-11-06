"""基于空间梁截面内力的四大强度理论校核。

此模块是整体梁模型的名义截面校核，不计算焊缝、孔洞或相贯线处的局部
应力集中。它以 D 定义圆形外缘代理并使用输入的 A、Iy、Iz、J 恢复应力；
当这些参数来自真实圆管时可作圆管校核，其他等效截面应仅作课程级比较。
剪力按截面平均剪应力恢复，扭转剪应力按圆管 Saint-Venant 解恢复。
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from framecae.core.model import Model
from framecae.solver.static_solver import StaticResult


THEORY_LABELS = {
    "rankine": "最大主应力理论 Rankine",
    "strain": "最大主应变理论 Saint-Venant",
    "tresca": "最大切应力理论 Tresca",
    "mises": "畸变能理论 von Mises",
}


@dataclass(frozen=True)
class StrengthCheckOptions:
    """强度校核材料限值与连续极值求解参数；周向点数字段只兼容旧接口。"""

    yield_strength: float = 355.0e6
    tensile_strength: float = 355.0e6
    compressive_strength: float = 355.0e6
    circumferential_points: int = 32
    include_average_transverse_shear: bool = True
    extremum_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        if min(self.yield_strength, self.tensile_strength, self.compressive_strength) <= 0.0:
            raise ValueError("强度限值必须为正数。")
        if not np.isfinite(self.extremum_tolerance) or not 1e-10 <= self.extremum_tolerance <= 1e-2:
            raise ValueError("极值相对容差应位于 1e-10 到 1e-2。")
        if not 8 <= self.circumferential_points <= 128:
            raise ValueError("圆管周向采样点数应位于 8 到 128。")


@dataclass(frozen=True)
class StrengthPoint:
    """杆件截面外缘一个周向点的三维名义应力状态。"""

    element_id: int
    position: float
    angle: float
    global_position: np.ndarray
    forces: np.ndarray
    stress_tensor: np.ndarray
    principal_stresses: np.ndarray
    equivalents: dict[str, float]
    utilizations: dict[str, float]


def evaluate_strength_point(
    element, position: float, forces: np.ndarray, angle: float,
    options: StrengthCheckOptions,
) -> StrengthPoint:
    """恢复圆管外缘一点的应力张量及四种理论利用率。"""
    section, material = element.section, element.material
    outer, _ = _tube_radii(section.area, section.characteristic_size)
    y, z = outer * np.cos(angle), outer * np.sin(angle)
    axial, shear_y, shear_z, torsion, moment_y, moment_z = np.asarray(forces, dtype=float)
    sigma_x = axial / section.area + moment_y * z / section.iy + moment_z * y / section.iz
    # 圆管扭转：tau_xy=-T z/J，tau_xz=T y/J。横向剪力仅能在没有截面
    # 剪切面积参数时按平均值处理，结果会在输出中明确说明。
    tau_xy = -torsion * z / section.torsion_constant
    tau_xz = torsion * y / section.torsion_constant
    if options.include_average_transverse_shear:
        tau_xy += shear_y / section.area
        tau_xz += shear_z / section.area
    tensor = np.array(
        [[sigma_x, tau_xy, tau_xz], [tau_xy, 0.0, 0.0], [tau_xz, 0.0, 0.0]],
        dtype=float,
    )
    principal = np.linalg.eigvalsh(tensor)[::-1]
    equivalents = _equivalent_stresses(principal, material.poisson_ratio)
    utilizations = {
        "rankine": max(
            max(principal[0], 0.0) / options.tensile_strength,
            max(-principal[-1], 0.0) / options.compressive_strength,
        ),
        "strain": equivalents["strain"] / options.yield_strength,
        "tresca": equivalents["tresca"] / options.yield_strength,
        "mises": equivalents["mises"] / options.yield_strength,
    }
    local_vector = np.array([position, y, z], dtype=float)
    global_position = element.start_node.coordinates + element.rotation.T @ local_vector
    return StrengthPoint(
        element.id, float(position), float(angle), global_position, np.asarray(forces, dtype=float),
        tensor, principal, equivalents, utilizations,
    )


def check_model_strength(
    model: Model, result: StaticResult, options: StrengthCheckOptions | None = None,
) -> dict:
    """分段求解圆管连续强度极值，返回四种理论各自的危险位置。"""
    options = options or StrengthCheckOptions()
    from .direct_strength import member_extrema
    critical={};member_maxima={};skipped=[];count=0;diagnostics={}
    for element in model.elements.values():
        try:_tube_radii(element.section.area,element.section.characteristic_size)
        except ValueError:skipped.append(element.id);continue
        answers,number,details=member_extrema(model,result,element,options)
        count+=number;diagnostics[element.id]=details
        member_maxima[element.id]={k:p.utilizations[k] for k,p in answers.items()}
        for k,p in answers.items():
            if k not in critical or p.utilizations[k]>critical[k].utilizations[k]:critical[k]=p
    if not critical:raise ValueError("模型中没有可由 A 与 D 识别的空心圆管截面。")
    return {'critical':critical,'member_maxima':member_maxima,'point_count':count,
        'skipped_elements':skipped,'options':options,'method':'directPiecewiseExtrema',
        'extremumTolerance':options.extremum_tolerance,'searchDiagnostics':diagnostics}


def _equivalent_stresses(principal: np.ndarray, poisson_ratio: float) -> dict[str, float]:
    first, second, third = principal
    maximum_strain_equivalent = max(abs(first - poisson_ratio * (second + third)),
                                    abs(second - poisson_ratio * (first + third)),
                                    abs(third - poisson_ratio * (first + second)))
    maximum_shear_equivalent = max(abs(first - second), abs(second - third), abs(third - first))
    mises = np.sqrt(0.5 * ((first - second) ** 2 + (second - third) ** 2 + (third - first) ** 2))
    return {
        "rankine": float(max(abs(principal))),
        "strain": float(maximum_strain_equivalent),
        "tresca": float(maximum_shear_equivalent),
        "mises": float(mises),
    }


def _tube_radii(area: float, diameter: float) -> tuple[float, float]:
    outer = diameter / 2.0
    inner_squared = outer**2 - area / np.pi
    if inner_squared <= 0.0:
        raise ValueError("截面不是由 A 与 D 定义的空心圆管。")
    return outer, float(np.sqrt(inner_squared))
