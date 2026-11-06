"""Euler-Bernoulli 三维空间刚架单元。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from framecae.core.material import Material
from framecae.core.node import Node
from framecae.core.section import Section
from framecae.elements.transformation import local_axes, transformation_matrix


@dataclass
class Frame3D:
    """两节点、每节点六自由度的三维 Euler-Bernoulli 刚架单元。

    局部自由度顺序为
    ``[u1, v1, w1, rx1, ry1, rz1, u2, v2, w2, rx2, ry2, rz2]``。
    其中局部 x 沿杆轴，局部 y/z 为截面主轴。第一版不含剪切变形，后续可
    在保持此接口的前提下加入 Timoshenko 梁修正。
    """

    id: int
    start_node: Node
    end_node: Node
    material: Material
    section: Section
    reference_vector: np.ndarray | None = None

    @property
    def length(self) -> float:
        """返回未变形构形下的单元长度。"""
        return float(np.linalg.norm(self.end_node.coordinates - self.start_node.coordinates))

    @property
    def rotation(self) -> np.ndarray:
        """返回全局向量到局部向量的方向余弦矩阵。"""
        return local_axes(
            self.start_node.coordinates,
            self.end_node.coordinates,
            self.reference_vector,
        )

    @property
    def transformation(self) -> np.ndarray:
        """返回单元 12×12 坐标变换矩阵。"""
        return transformation_matrix(self.rotation)

    def local_stiffness(self) -> np.ndarray:
        """计算局部坐标系下的 12×12 线弹性刚度矩阵。

        包含 EA/L 轴向刚度、GJ/L 扭转刚度、EIz 控制的 v-rz 弯曲以及
        EIy 控制的 w-ry 弯曲。矩阵按能量共轭的位移和转角符号构造。
        """
        length = self.length
        if length <= 0.0:
            raise ValueError("单元长度必须大于零。")

        e_modulus = self.material.elastic_modulus
        shear_modulus = self.material.shear_modulus
        area = self.section.area
        iy = self.section.iy
        iz = self.section.iz
        torsion_constant = self.section.torsion_constant
        stiffness = np.zeros((12, 12), dtype=float)

        axial = e_modulus * area / length
        stiffness[np.ix_([0, 6], [0, 6])] = axial * np.array([[1.0, -1.0], [-1.0, 1.0]])

        torsion = shear_modulus * torsion_constant / length
        stiffness[np.ix_([3, 9], [3, 9])] = torsion * np.array([[1.0, -1.0], [-1.0, 1.0]])

        # v-rz 平面：绕局部 z 的弯曲刚度为 EIz。
        bending_z = e_modulus * iz * np.array(
            [
                [12.0 / length**3, 6.0 / length**2, -12.0 / length**3, 6.0 / length**2],
                [6.0 / length**2, 4.0 / length, -6.0 / length**2, 2.0 / length],
                [-12.0 / length**3, -6.0 / length**2, 12.0 / length**3, -6.0 / length**2],
                [6.0 / length**2, 2.0 / length, -6.0 / length**2, 4.0 / length],
            ]
        )
        stiffness[np.ix_([1, 5, 7, 11], [1, 5, 7, 11])] = bending_z

        # w-ry 平面：因右手转角约定，w 与 ry 的耦合项符号相反。
        bending_y = e_modulus * iy * np.array(
            [
                [12.0 / length**3, -6.0 / length**2, -12.0 / length**3, -6.0 / length**2],
                [-6.0 / length**2, 4.0 / length, 6.0 / length**2, 2.0 / length],
                [-12.0 / length**3, 6.0 / length**2, 12.0 / length**3, 6.0 / length**2],
                [-6.0 / length**2, 2.0 / length, 6.0 / length**2, 4.0 / length],
            ]
        )
        stiffness[np.ix_([2, 4, 8, 10], [2, 4, 8, 10])] = bending_y

        return stiffness

    def global_stiffness(self) -> np.ndarray:
        """计算全局坐标系下的 12×12 单元刚度矩阵。"""
        transform = self.transformation
        return transform.T @ self.local_stiffness() @ transform

    def local_thermal_load(self, delta_temperature: float) -> np.ndarray:
        """返回均匀温差引起的局部等效节点荷载向量。

        仅考虑沿杆轴的均匀温度应变 ``ε_th=αΔT``。该荷载被加入总体右端项，
        因而一端自由时产生自由伸长 ``αΔTL``，两端约束时产生热轴力。
        """
        thermal_force = (
            self.material.elastic_modulus
            * self.section.area
            * self.material.thermal_expansion
            * float(delta_temperature)
        )
        load = np.zeros(12, dtype=float)
        load[0] = -thermal_force
        load[6] = thermal_force
        return load

    def global_thermal_load(self, delta_temperature: float) -> np.ndarray:
        """将局部等效热荷载转换到全局坐标系。"""
        return self.transformation.T @ self.local_thermal_load(delta_temperature)

    def local_uniform_load(self, components: np.ndarray) -> np.ndarray:
        """计算局部均布线荷载 [qx, qy, qz] 的 12 分量一致等效节点荷载。

        qy 作用于 v-rz 平面，qz 作用于 w-ry 平面；弯曲转角项的符号与本项目
        的局部自由度约定一致。荷载正方向与局部 x、y、z 轴正方向一致。
        """
        qx, qy, qz = np.asarray(components, dtype=float)
        length = self.length
        loads = np.zeros(12, dtype=float)
        loads[[0, 6]] = qx * length / 2.0
        loads[[1, 7]] = qy * length / 2.0
        loads[5] = qy * length**2 / 12.0
        loads[11] = -qy * length**2 / 12.0
        loads[[2, 8]] = qz * length / 2.0
        loads[4] = -qz * length**2 / 12.0
        loads[10] = qz * length**2 / 12.0
        return loads

    def local_point_load(self, position: float, components: np.ndarray) -> np.ndarray:
        """计算杆上局部集中力 [Px, Py, Pz] 的一致等效节点荷载。

        ``position`` 从单元起点沿局部 x 轴量起。横向荷载使用三次 Hermite 位移
        形函数，因而可同时正确传递节点剪力与节点弯矩。
        """
        length = self.length
        if not 0.0 <= position <= length:
            raise ValueError("杆上集中力位置必须位于 [0, L] 内。")
        px, py, pz = np.asarray(components, dtype=float)
        ratio = position / length
        n1 = 1.0 - 3.0 * ratio**2 + 2.0 * ratio**3
        n2 = length * (ratio - 2.0 * ratio**2 + ratio**3)
        n3 = 3.0 * ratio**2 - 2.0 * ratio**3
        n4 = length * (-ratio**2 + ratio**3)
        loads = np.zeros(12, dtype=float)
        loads[[0, 6]] = px * np.array([1.0 - ratio, ratio])
        loads[[1, 5, 7, 11]] = py * np.array([n1, n2, n3, n4])
        # w 与 ry 的符号约定和 v 与 rz 相反，故转角形函数取相反号。
        loads[[2, 4, 8, 10]] = pz * np.array([n1, -n2, n3, -n4])
        return loads
