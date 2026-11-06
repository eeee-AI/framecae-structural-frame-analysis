"""作用在空间刚架杆件上的局部荷载定义。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UniformMemberLoad:
    """局部坐标系下沿整根杆件均匀分布的线荷载 [qx, qy, qz]，单位 N/m。"""

    local_components: np.ndarray
    coordinate_system: str = "local"
    input_components: tuple | None = None

    def __post_init__(self) -> None:
        components = np.asarray(self.local_components, dtype=float)
        if components.shape != (3,):
            raise ValueError("均布荷载必须包含 [qx, qy, qz] 三个局部分量。")
        object.__setattr__(self, "local_components", components)


@dataclass(frozen=True)
class PointMemberLoad:
    """局部坐标系下的杆上集中力 [Px, Py, Pz]，位置从杆件起点沿 x 轴量起。"""

    position: float
    local_components: np.ndarray
    coordinate_system: str = "local"
    input_components: tuple | None = None

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("杆上集中力位置不能小于零。")
        components = np.asarray(self.local_components, dtype=float)
        if components.shape != (3,):
            raise ValueError("杆上集中力必须包含 [Px, Py, Pz] 三个局部分量。")
        object.__setattr__(self, "local_components", components)
