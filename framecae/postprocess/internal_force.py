"""沿空间刚架杆件任意位置恢复内力与名义正应力。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from framecae.core.member_load import PointMemberLoad, UniformMemberLoad
from framecae.core.model import Model
from framecae.postprocess.element_force import recover_element_end_force
from framecae.solver.static_solver import StaticResult


@dataclass(frozen=True)
class SectionResult:
    """局部 x 位置的内力与截面名义应力结果。"""

    position: float
    forces: np.ndarray
    nominal_stress: float


def evaluate_section(
    model: Model, result: StaticResult, element_id: int, position: float
) -> SectionResult:
    """恢复杆件在局部坐标 x=position 处的 [N, Vy, Vz, T, My, Mz]。

    截面内力从局部起端内力出发，按杆上均布荷载和集中力逐段积分。弯矩符号
    满足 ``dMz/dx=-Vy`` 与 ``dMy/dx=Vz``；所有结果使用本项目的局部坐标和
    杆端力符号约定。
    """
    element = model.elements[element_id]
    if not 0.0 <= position <= element.length:
        raise ValueError(f"截面位置必须位于 [0, {element.length:g}] 内。")
    start_force = recover_element_end_force(model, result, element_id).start
    forces = start_force.copy()
    # 截面弯矩首先由起端剪力沿 x 方向传递。
    forces[4] += start_force[2] * position
    forces[5] -= start_force[1] * position

    for load in model.member_loads.get(element_id, []):
        if isinstance(load, UniformMemberLoad):
            qx, qy, qz = load.local_components
            forces[0] += qx * position
            forces[1] += qy * position
            forces[2] += qz * position
            forces[4] += qz * position**2 / 2.0
            forces[5] -= qy * position**2 / 2.0
        elif position >= load.position:
            px, py, pz = load.local_components
            arm = position - load.position
            forces[0] += px
            forces[1] += py
            forces[2] += pz
            forces[4] += pz * arm
            forces[5] -= py * arm

    # 自重不是手动杆上荷载的一部分，但在沿程内力恢复中必须同样积分。
    qx, qy, qz = model.local_self_weight_components(element_id)
    forces[0] += qx * position
    forces[1] += qy * position
    forces[2] += qz * position
    forces[4] += qz * position**2 / 2.0
    forces[5] -= qy * position**2 / 2.0

    return SectionResult(
        position=float(position),
        forces=forces,
        nominal_stress=_maximum_nominal_stress(element.section, forces),
    )


def sample_element_sections(
    model: Model, result: StaticResult, element_id: int, count: int = 41
) -> list[SectionResult]:
    """沿杆等距采样内力；遇到集中力位置时额外插入该位置。"""
    if count < 2:
        raise ValueError("沿杆采样点数至少为 2。")
    element = model.elements[element_id]
    locations = list(np.linspace(0.0, element.length, count))
    for load in model.member_loads.get(element_id, []):
        if isinstance(load, PointMemberLoad):
            # 集中力处剪力会跳跃；显式保留作用点左右两侧，供沿程内力图正确绘制。
            offset = min(element.length * 1.0e-7, 1.0e-7)
            locations.extend((
                max(0.0, load.position - offset), load.position,
                min(element.length, load.position + offset),
            ))
    locations.extend(_nominal_stress_stationary_positions(model, result, element_id))
    return [evaluate_section(model, result, element_id, position) for position in sorted(set(locations))]


def _nominal_stress_stationary_positions(
    model: Model, result: StaticResult, element_id: int
) -> list[float]:
    """补充均布荷载分段内名义应力的驻点，避免沿杆等距采样漏掉峰值。"""
    element = model.elements[element_id]
    section = element.section
    point_locations = sorted({
        load.position for load in model.member_loads.get(element_id, [])
        if isinstance(load, PointMemberLoad) and 0.0 < load.position < element.length
    })
    boundaries = [0.0, *point_locations, element.length]
    uniform = sum(
        (load.local_components for load in model.member_loads.get(element_id, [])
         if isinstance(load, UniformMemberLoad)),
        start=np.zeros(3),
    )
    uniform += model.local_self_weight_components(element_id)
    qx, qy, qz = uniform
    extreme = section.characteristic_size / 2.0
    tolerance = element.length * 1.0e-10
    positions: list[float] = []
    for lower, upper in zip(boundaries, boundaries[1:]):
        forces = evaluate_section(model, result, element_id, lower).forces
        for y in (-extreme, extreme):
            for z in (-extreme, extreme):
                linear = qx / section.area + forces[2] * z / section.iy - forces[1] * y / section.iz
                quadratic = 0.5 * (qz * z / section.iy - qy * y / section.iz)
                if abs(quadratic) <= 1.0e-18:
                    continue
                position = lower - linear / (2.0 * quadratic)
                if lower + tolerance < position < upper - tolerance:
                    positions.append(float(position))
    return positions


def _maximum_nominal_stress(section: object, forces: np.ndarray) -> float:
    """返回四个极纤维点中绝对值最大的梁模型名义正应力。

    当前 Section 只有统一的特征尺寸 D，因此第一版取局部 y、z 两方向极纤维
    距离均为 D/2。后续若补充真实截面边界参数，可在此替换为精确纤维坐标。
    """
    axial, _, _, _, moment_y, moment_z = forces
    extreme = section.characteristic_size / 2.0
    stresses = [
        axial / section.area + moment_y * z / section.iy + moment_z * y / section.iz
        for y in (-extreme, extreme)
        for z in (-extreme, extreme)
    ]
    return float(max(stresses, key=abs))


def element_force_segments(model, result, element_id):
    """Piecewise quadratic force polynomials in normalized interval coordinate t.
    Constant/linear coefficients preserve exact left limits at point loads.
    """
    e=model.elements[element_id]
    knots=sorted({0.,e.length,*[load.position for load in model.member_loads.get(element_id,[])
        if isinstance(load,PointMemberLoad) and 0 < load.position < e.length]})
    uniform=sum((load.local_components for load in model.member_loads.get(element_id,[]) if isinstance(load,UniformMemberLoad)),start=np.zeros(3))+model.local_self_weight_components(element_id)
    qx,qy,qz=uniform
    records=[]
    for lower,upper in zip(knots,knots[1:]):
        f=evaluate_section(model,result,element_id,lower).forces;length=upper-lower
        linear=np.array([qx*length,qy*length,qz*length,0.,f[2]*length,-f[1]*length])
        quadratic=np.array([0.,0.,0.,0.,qz*length**2/2,-qy*length**2/2])
        records.append((lower,upper,f,linear,quadratic))
    return records


