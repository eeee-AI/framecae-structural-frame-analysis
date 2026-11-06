"""对称刚度矩阵的自编 LDLᵀ 三角分解与回代求解。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LDLTFactorization:
    """实对称矩阵的单位下三角 L 与对角阵 D。

    对线弹性、约束充分的刚架刚度矩阵，有 ``K = L D Lᵀ``。保存分解结果后，
    对不同荷载工况只需重复前代、对角求解和回代，无须重新三角分解。
    """

    lower: np.ndarray
    diagonal: np.ndarray

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        """按前代 → 对角求解 → 回代的顺序求解 Kx=b。"""
        vector = np.asarray(right_hand_side, dtype=float)
        size = self.diagonal.size
        if vector.shape != (size,):
            raise ValueError("右端荷载向量长度与刚度矩阵维数不一致。")

        # 前代：L y = b
        forward = np.empty(size, dtype=float)
        for row in range(size):
            forward[row] = vector[row] - np.dot(self.lower[row, :row], forward[:row])

        # 对角阵求解：D z = y
        diagonal_solution = forward / self.diagonal

        # 回代：Lᵀ x = z
        displacement = np.empty(size, dtype=float)
        for row in range(size - 1, -1, -1):
            displacement[row] = diagonal_solution[row] - np.dot(
                self.lower[row + 1 :, row], displacement[row + 1 :]
            )
        return displacement


def ldlt_factor(stiffness: np.ndarray, tolerance: float = 1.0e-12) -> LDLTFactorization:
    """对实对称刚度矩阵实施无主元 LDLᵀ 三角分解。

    本函数直接体现课程程序框图中的“总刚度矩阵三角化”。对正确施加边界条件
    的线弹性结构，约化刚度矩阵应为正定；若出现接近零或负的 D 对角元，通常
    表示支座约束不足、存在刚体位移或模型不稳定。
    """
    matrix = np.asarray(stiffness, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("LDLᵀ 分解要求输入方阵。")
    if not np.allclose(matrix, matrix.T, rtol=1.0e-10, atol=1.0e-8):
        raise ValueError("刚度矩阵必须对称。")

    size = matrix.shape[0]
    lower = np.eye(size, dtype=float)
    diagonal = np.empty(size, dtype=float)
    scale = max(float(np.max(np.abs(np.diag(matrix)))), 1.0)
    pivot_limit = tolerance * scale

    for row in range(size):
        for column in range(row):
            coupling = matrix[row, column] - np.dot(
                lower[row, :column] * diagonal[:column], lower[column, :column]
            )
            lower[row, column] = coupling / diagonal[column]
        diagonal[row] = matrix[row, row] - np.dot(
            lower[row, :row] ** 2, diagonal[:row]
        )
        if diagonal[row] <= pivot_limit:
            raise ValueError(
                "刚度矩阵三角分解失败："
                f"第 {row + 1} 个主元为 {diagonal[row]:.3e}。"
                "请检查支座约束、杆件连接和模型稳定性。"
            )
    return LDLTFactorization(lower=lower, diagonal=diagonal)


def solve_ldlt(stiffness: np.ndarray, loads: np.ndarray) -> np.ndarray:
    """一次性完成三角分解、前代、对角求解和回代。"""
    return ldlt_factor(stiffness).solve(loads)
