"""空间刚架单元的局部杆端力恢复。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from framecae.core.model import Model
from framecae.solver.static_solver import StaticResult


@dataclass(frozen=True)
class ElementEndForces:
    """单元局部杆端力。

    ``local_vector`` 顺序与单元局部自由度一致，其各节点六分量依次为
    ``[N, Vy, Vz, T, My, Mz]``。这里的端力为单元对节点的内力，已扣除均匀
    温度应变与制造长度偏差造成的初应变等效荷载，以及杆上与自重荷载。
    """

    element_id: int
    local_vector: np.ndarray

    @property
    def start(self) -> np.ndarray:
        return self.local_vector[:6].copy()

    @property
    def end(self) -> np.ndarray:
        return self.local_vector[6:].copy()


def recover_element_end_force(model: Model, result: StaticResult, element_id: int) -> ElementEndForces:
    """仅恢复指定杆件，避免截面采样时反复计算全部杆件。"""
    element = model.elements[element_id]
    element_displacement_global = result.displacements[model.element_dofs(element)]
    element_displacement_local = element.transformation @ element_displacement_global
    delta_temperature = model.element_temperature_changes.get(element_id, 0.0)
    local_force = (
        element.local_stiffness() @ element_displacement_local
        - element.local_thermal_load(delta_temperature)
        - model.local_member_equivalent_load(element_id)
        - model.local_self_weight_equivalent_load(element_id)
        - model.local_assembly_equivalent_load(element_id)
    )
    return ElementEndForces(element_id, local_force)


def recover_element_end_forces(model: Model, result: StaticResult) -> dict[int, ElementEndForces]:
    """由整体位移恢复每根杆件局部坐标系下的端部内力。"""
    return {element_id: recover_element_end_force(model, result, element_id)
            for element_id in model.elements}
