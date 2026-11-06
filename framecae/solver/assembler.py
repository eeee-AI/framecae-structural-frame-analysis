"""使用 COO→CSR 稀疏格式组装空间刚架总体方程。"""

from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from framecae.core.model import Model


def assemble_stiffness(model: Model) -> csr_matrix:
    """由全部单元全局刚度矩阵组装总体 CSR 刚度矩阵。"""
    total_dofs = model.number_dofs()
    if not model.elements:
        raise ValueError("模型至少需要一个单元。")

    row_indices: list[np.ndarray] = []
    column_indices: list[np.ndarray] = []
    values: list[np.ndarray] = []
    for element in model.elements.values():
        element_dofs = model.element_dofs(element)
        row_indices.append(np.repeat(element_dofs, 12))
        column_indices.append(np.tile(element_dofs, 12))
        values.append(element.global_stiffness().reshape(-1))

    stiffness = coo_matrix(
        (np.concatenate(values), (np.concatenate(row_indices), np.concatenate(column_indices))),
        shape=(total_dofs, total_dofs),
    ).tocsr()
    # 梁单元合同变换及 COO 重复项求和都可能产生末位舍入差。
    # 总刚度在数学上对称；组装后恢复这一性质，避免斜杆贡献相消时
    # 接近零的项误触发 LDLᵀ 的对称性检查。
    return ((stiffness + stiffness.T) * 0.5).tocsr()


def assemble_load_vector(model: Model) -> np.ndarray:
    """组装节点、温度、杆上及构件自重荷载形成总体荷载向量。"""
    load_vector = np.zeros(model.number_dofs(), dtype=float)
    for node_id, components in model.nodal_loads.items():
        node = model.nodes[node_id]
        load_vector[node.dof_indices] += components
    for element_id, delta_temperature in model.element_temperature_changes.items():
        element = model.elements[element_id]
        load_vector[model.element_dofs(element)] += element.global_thermal_load(delta_temperature)
    for element_id in model.member_loads:
        element = model.elements[element_id]
        load_vector[model.element_dofs(element)] += model.global_member_equivalent_load(element_id)
    if model.self_weight_enabled:
        for element_id, element in model.elements.items():
            load_vector[model.element_dofs(element)] += model.global_self_weight_equivalent_load(element_id)
    for element_id, delta_length in model.element_length_deviations.items():
        if delta_length != 0.0:
            element = model.elements[element_id]
            load_vector[model.element_dofs(element)] += model.global_assembly_equivalent_load(element_id)
    return load_vector
