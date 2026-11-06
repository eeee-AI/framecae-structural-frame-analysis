"""节点定义。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Node:
    """空间刚架节点。

    节点自由度的顺序固定为 ``[ux, uy, uz, rx, ry, rz]``。其中前三项为
    全局坐标系平动，后三项为绕全局 x、y、z 轴的右手正向转角。
    ``dof_indices`` 由后续的 ``Model`` 类统一编号，不能由节点编号推断，
    以支持不连续的节点编号。
    """

    id: int
    x: float
    y: float
    z: float
    dof_indices: np.ndarray | None = field(default=None, init=False, repr=False)

    @property
    def coordinates(self) -> np.ndarray:
        """以 ``[x, y, z]`` 形式返回节点的全局坐标。"""
        return np.array([self.x, self.y, self.z], dtype=float)

    def assign_dofs(self, start_index: int) -> None:
        """从 ``start_index`` 起为该节点分配连续的六个全局自由度。"""
        if start_index < 0:
            raise ValueError("自由度起始编号不能为负数。")
        self.dof_indices = np.arange(start_index, start_index + 6, dtype=int)

