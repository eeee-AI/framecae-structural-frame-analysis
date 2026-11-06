"""从整体空间梁单元恢复任意截断面的位移和转角。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from framecae.core.model import Model
from framecae.elements.frame3d import Frame3D
from framecae.solver.static_solver import StaticResult
from framecae.postprocess.displacement import build_element_curve, polynomial_value


@dataclass(frozen=True)
class BeamSectionState:
    """梁截断面的全局平动和小转角。"""

    position: float
    translation: np.ndarray
    rotation: np.ndarray


def interpolate_beam_section(
    model: Model, result: StaticResult, element_id: int, position: float
) -> BeamSectionState:
    """用 Euler–Bernoulli 形函数恢复杆件局部 x=position 截断面运动。

    共用 01 的分段位移函数，保留节点 Hermite 项、杆内集中力/均布力及自重
    特解。弯曲转角来自同一函数的解析导数，扭转转角采用节点线性插值。
    输出已转换到全局坐标，可直接用于局部实体截断面位移映射。
    """
    element = model.elements[element_id]
    length = element.length
    if not np.isfinite(position) or not 0.0 <= position <= length:
        raise ValueError(f"梁截断面位置必须位于 [0, {length:g}] 内。")
    dofs = model.element_dofs(element)
    local = element.transformation @ result.displacements[dofs]
    ratio = position / length
    # 与 01 共用同一分段位移多项式，包括杆内集中力、均布力及自重特解。
    # 系数使用各段的归一化参数 t，求导后必须除以该段实际长度。
    curve = build_element_curve(model, result, element_id)
    segment = next(part for part in curve["segments"] if position <= part["x1"])
    width = segment["x1"] - segment["x0"]
    parameter = (position - segment["x0"]) / width
    coefficients = np.asarray(segment["displacementCoefficients"])
    translation = polynomial_value(coefficients, parameter)
    derivative = coefficients[1:] * np.arange(1, len(coefficients))[:, None] / width
    local_slope = element.rotation @ polynomial_value(derivative, parameter)
    local_rotation = np.array([
        (1.0 - ratio) * local[3] + ratio * local[9],
        -local_slope[2],
        local_slope[1],
    ])
    return BeamSectionState(
        position=float(position),
        translation=translation,
        rotation=element.rotation.T @ local_rotation,
    )
