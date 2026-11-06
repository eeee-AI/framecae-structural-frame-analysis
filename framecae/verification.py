"""课程核心功能的解析解验证算例。"""

from __future__ import annotations

from dataclasses import dataclass

from framecae.core.material import Material
from framecae.core.model import Model
from framecae.core.node import Node
from framecae.core.section import Section
from framecae.elements.frame3d import Frame3D
from framecae.postprocess.element_force import recover_element_end_forces
from framecae.solver.static_solver import StaticSolver


@dataclass(frozen=True)
class VerificationQuantity:
    """一项数值结果和对应解析解。"""

    name: str
    unit: str
    numerical: float
    analytical: float

    @property
    def relative_error(self) -> float:
        return abs(self.numerical - self.analytical) / max(abs(self.analytical), 1.0e-18)


def run_global_verifications() -> list[VerificationQuantity]:
    """计算悬臂梁与完全约束温度杆的课程级解析解对比。"""
    return [*_cantilever_verification(), *_thermal_bar_verification()]


def _cantilever_verification() -> list[VerificationQuantity]:
    length, force = 3.0, -10_000.0
    material = Material(1, 210.0e9, 0.30)
    section = Section(1, 4.0e-3, 5.0e-6, 8.0e-6, 1.0e-5, 0.12)
    model = Model()
    model.add_node(Node(1, 0.0, 0.0, 0.0))
    model.add_node(Node(2, length, 0.0, 0.0))
    model.add_element(Frame3D(1, model.nodes[1], model.nodes[2], material, section))
    model.fix_node(1)
    model.add_nodal_load(2, [0.0, 0.0, force, 0.0, 0.0, 0.0])
    result = StaticSolver().solve(model)
    tip = result.node_displacement(model, 2)
    return [
        VerificationQuantity(
            "悬臂梁自由端竖向位移 uz", "m", tip[2],
            force * length**3 / (3.0 * material.elastic_modulus * section.iz),
        ),
        VerificationQuantity(
            "悬臂梁自由端转角 ry", "rad", tip[4],
            -force * length**2 / (2.0 * material.elastic_modulus * section.iz),
        ),
    ]


def _thermal_bar_verification() -> list[VerificationQuantity]:
    delta_temperature = 50.0
    material = Material(1, 200.0e9, 0.30, thermal_expansion=1.2e-5)
    section = Section(1, 2.5e-3, 1.0e-6, 1.0e-6, 2.0e-6, 0.08)
    model = Model()
    model.add_node(Node(1, 0.0, 0.0, 0.0))
    model.add_node(Node(2, 2.0, 0.0, 0.0))
    model.add_element(Frame3D(1, model.nodes[1], model.nodes[2], material, section))
    model.fix_node(1)
    model.fix_node(2)
    model.set_element_temperature_change(1, delta_temperature)
    result = StaticSolver().solve(model)
    force = recover_element_end_forces(model, result)[1].start[0]
    return [
        VerificationQuantity(
            "完全约束温度杆热轴力 N", "N", force,
            material.elastic_modulus * section.area * material.thermal_expansion * delta_temperature,
        ),
        VerificationQuantity(
            "完全约束温度杆热应力 σ", "Pa", force / section.area,
            material.elastic_modulus * material.thermal_expansion * delta_temperature,
        ),
    ]
