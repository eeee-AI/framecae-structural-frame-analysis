"""各向同性线弹性材料定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    """材料参数。

    所有计算采用 SI 单位：E 为 Pa，density 为 kg/m³，thermal_expansion
    为 1/K。后续温度应力模块将直接使用 ``thermal_expansion``。
    """

    id: int
    elastic_modulus: float
    poisson_ratio: float
    density: float = 7850.0
    thermal_expansion: float = 1.2e-5

    def __post_init__(self) -> None:
        if self.elastic_modulus <= 0:
            raise ValueError("弹性模量 E 必须为正数。")
        if not -1.0 < self.poisson_ratio < 0.5:
            raise ValueError("泊松比必须位于 (-1, 0.5) 内。")
        if self.density < 0:
            raise ValueError("密度不能为负数。")
        if self.thermal_expansion < 0:
            raise ValueError("线膨胀系数不能为负数。")

    @property
    def shear_modulus(self) -> float:
        """返回各向同性材料的剪切模量 G=E/[2(1+ν)]。"""
        return self.elastic_modulus / (2.0 * (1.0 + self.poisson_ratio))

