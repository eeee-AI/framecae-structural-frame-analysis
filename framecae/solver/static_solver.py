"""基于位移法的线性静力求解器。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

from framecae.core.model import Model
from framecae.solver.assembler import assemble_load_vector, assemble_stiffness
from framecae.solver.ldlt import solve_ldlt


@dataclass(frozen=True)
class StaticResult:
    """线性静力计算结果。"""

    displacements: np.ndarray
    reactions: np.ndarray
    stiffness: csr_matrix
    loads: np.ndarray
    solution_method: str

    def node_displacement(self, model: Model, node_id: int) -> np.ndarray:
        """返回一个节点的 ``[ux, uy, uz, rx, ry, rz]`` 结果。"""
        node = model.nodes[node_id]
        if node.dof_indices is None:
            raise ValueError("模型尚未完成自由度编号。")
        return self.displacements[node.dof_indices].copy()


class StaticSolver:
    """求解 ``Kff uf = Ff - Kfc uc``，并恢复支座反力。

    默认采用自编 LDLᵀ 三角分解，以逐步对应课程的“刚度矩阵三角化—回代”
    流程；``method='scipy'`` 仅作为大规模稀疏模型的可选加速路径。
    """

    def __init__(self, method: str = "ldlt", max_ldlt_dofs: int = 2_000) -> None:
        if method not in {"ldlt", "scipy"}:
            raise ValueError("求解方法只能是 'ldlt' 或 'scipy'。")
        if max_ldlt_dofs <= 0:
            raise ValueError("LDLᵀ 最大自由度数必须为正数。")
        self.method = method
        self.max_ldlt_dofs = max_ldlt_dofs

    def solve(self, model: Model) -> StaticResult:
        """完成稀疏刚度组装、边界条件处理和线性静力求解。"""
        stiffness = assemble_stiffness(model)
        loads = assemble_load_vector(model)
        total_dofs = model.number_dofs()
        constraints = model.constrained_dof_values()

        constrained = np.array(sorted(constraints), dtype=int)
        free = np.setdiff1d(np.arange(total_dofs), constrained, assume_unique=True)
        displacements = np.zeros(total_dofs, dtype=float)
        if constrained.size:
            displacements[constrained] = [constraints[index] for index in constrained]

        if free.size:
            reduced_stiffness = stiffness[free][:, free]
            reduced_loads = loads[free]
            if constrained.size:
                reduced_loads -= stiffness[free][:, constrained] @ displacements[constrained]
            if self.method == "ldlt":
                if free.size > self.max_ldlt_dofs:
                    raise ValueError(
                        f"当前自由度数为 {free.size}，超过自编 LDLᵀ 的 {self.max_ldlt_dofs} 上限。"
                        "请提高上限，或显式使用 StaticSolver(method='scipy') 求解大规模模型。"
                    )
                displacements[free] = solve_ldlt(reduced_stiffness.toarray(), reduced_loads)
            else:
                displacements[free] = spsolve(reduced_stiffness, reduced_loads)
        if not np.all(np.isfinite(displacements)):
            raise ValueError("求解失败：模型可能存在刚体位移或刚度矩阵奇异。")

        reactions = stiffness @ displacements - loads
        return StaticResult(
            displacements=displacements,
            reactions=np.asarray(reactions),
            stiffness=stiffness,
            loads=loads,
            solution_method=self.method,
        )
