"""梁截面定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """局部截面参数。

    ``iy`` 和 ``iz`` 分别是绕局部 y、z 轴的截面二次矩；``torsion_constant``
    为 Saint-Venant 扭转常数 J。``characteristic_size`` 用于后续局部实体
    子模型的截取长度与网格尺寸控制。
    """

    id: int
    area: float
    iy: float
    iz: float
    torsion_constant: float
    characteristic_size: float

    def __post_init__(self) -> None:
        values = {
            "截面面积 A": self.area,
            "截面二次矩 Iy": self.iy,
            "截面二次矩 Iz": self.iz,
            "扭转常数 J": self.torsion_constant,
            "特征尺寸 D": self.characteristic_size,
        }
        for name, value in values.items():
            if value <= 0:
                raise ValueError(f"{name} 必须为正数。")

