"""空间刚架有限元模型、节点荷载和位移约束。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from framecae.core.member_load import PointMemberLoad, UniformMemberLoad
from framecae.core.node import Node
from framecae.elements.frame3d import Frame3D

DOF_LABELS = ("ux", "uy", "uz", "rx", "ry", "rz")


@dataclass
class Model:
    """线弹性空间刚架模型。

    节点与单元编号由用户给出；整体自由度按节点编号从小到大的顺序自动分配。
    集中荷载与集中力矩均写入 ``nodal_loads`` 的六分量数组，约束字典的值为
    指定的位移或转角，因而同时支持固定、释放及非零支座位移。
    """

    nodes: dict[int, Node] = field(default_factory=dict)
    elements: dict[int, Frame3D] = field(default_factory=dict)
    nodal_loads: dict[int, np.ndarray] = field(default_factory=dict)
    element_temperature_changes: dict[int, float] = field(default_factory=dict)
    member_loads: dict[int, list[UniformMemberLoad | PointMemberLoad]] = field(default_factory=dict)
    prescribed_dofs: dict[tuple[int, int], float] = field(default_factory=dict)
    self_weight_enabled: bool = False
    gravity: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -9.81]))
    element_length_deviations: dict[int, float] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """加入一个节点；节点编号必须唯一。"""
        if node.id in self.nodes:
            raise ValueError(f"节点 {node.id} 已存在。")
        self.nodes[node.id] = node

    def add_element(self, element: Frame3D) -> None:
        """加入一个刚架单元，并确认其端节点已经属于本模型。"""
        if element.id in self.elements:
            raise ValueError(f"单元 {element.id} 已存在。")
        for node in (element.start_node, element.end_node):
            if self.nodes.get(node.id) is not node:
                raise ValueError(f"单元 {element.id} 的节点 {node.id} 未加入模型或对象不一致。")
        self.elements[element.id] = element

    def add_nodal_load(self, node_id: int, components: np.ndarray | list[float]) -> None:
        """叠加节点荷载 ``[Fx, Fy, Fz, Mx, My, Mz]``。"""
        self._require_node(node_id)
        load = np.asarray(components, dtype=float)
        if load.shape != (6,):
            raise ValueError("节点荷载必须包含 [Fx, Fy, Fz, Mx, My, Mz] 六个分量。")
        self.nodal_loads[node_id] = self.nodal_loads.get(node_id, np.zeros(6)) + load

    def set_element_temperature_change(self, element_id: int, delta_temperature: float) -> None:
        """设置单元均匀温差 ΔT，用于后续组装等效热荷载。

        温差单位可为 K 或 ℃；对于温差，两者数值相同。正值表示升温。
        """
        if element_id not in self.elements:
            raise ValueError(f"单元 {element_id} 不存在。")
        self.element_temperature_changes[element_id] = float(delta_temperature)

    def add_uniform_member_load(self, element_id: int, components: np.ndarray | list[float]) -> None:
        """加入一组局部均布线荷载 ``[qx, qy, qz]``，单位 N/m。"""
        self._require_element(element_id)
        self.member_loads.setdefault(element_id, []).append(UniformMemberLoad(np.asarray(components, dtype=float)))

    def add_point_member_load(
        self, element_id: int, position: float, components: np.ndarray | list[float]
    ) -> None:
        """加入局部杆上集中力 ``[Px, Py, Pz]``，位置从杆件起点量起。"""
        self._require_element(element_id)
        load = PointMemberLoad(float(position), np.asarray(components, dtype=float))
        if load.position > self.elements[element_id].length:
            raise ValueError(f"杆上集中力位置不能超过杆件 {element_id} 的长度。")
        self.member_loads.setdefault(element_id, []).append(load)

    def set_self_weight(self, enabled: bool, gravity: np.ndarray | list[float] | None = None) -> None:
        """设置构件自重开关及全局重力加速度 ``[gx, gy, gz]``。

        自重不写入 ``member_loads``，而在每次总体荷载组装时按各杆的
        ``rho*A*g`` 独立生成，避免重复求解时累计。
        """
        if gravity is not None:
            vector = np.asarray(gravity, dtype=float)
            if vector.shape != (3,) or not np.all(np.isfinite(vector)):
                raise ValueError("重力加速度必须是 [gx, gy, gz] 三个有限数。")
            self.gravity = vector.copy()
        self.self_weight_enabled = bool(enabled)

    def set_element_length_deviation(self, element_id: int, delta_length: float) -> None:
        """设置制造长度偏差 ``Δl=L制造-L设计``。

        ``Δl<0`` 表示杆件偏短，装配到设计节点位置时需要拉长；初始应变
        按 ``ε0=Δl/L`` 定义，恢复的单元轴力因此为拉力。偏差不写入节点
        荷载，避免重复求解时累计。
        """
        self._require_element(element_id)
        value = float(delta_length)
        if not np.isfinite(value):
            raise ValueError("杆件长度偏差必须是有限数字。")
        self.element_length_deviations[element_id] = value

    def prescribe_dof(self, node_id: int, dof: int, value: float = 0.0) -> None:
        """施加一个节点自由度的指定值，dof 顺序见 ``DOF_LABELS``。"""
        self._require_node(node_id)
        if dof not in range(6):
            raise ValueError("局部自由度编号必须是 0 到 5。")
        self.prescribed_dofs[(node_id, dof)] = float(value)

    def fix_node(self, node_id: int) -> None:
        """将节点的六个平动/转角自由度固定为零。"""
        for dof in range(6):
            self.prescribe_dof(node_id, dof)

    def number_dofs(self) -> int:
        """按节点编号排序分配整体自由度并返回总自由度数。"""
        for position, node_id in enumerate(sorted(self.nodes)):
            self.nodes[node_id].assign_dofs(6 * position)
        return 6 * len(self.nodes)

    def dof_index(self, node_id: int, dof: int) -> int:
        """返回节点某自由度的整体编号；自动确保自由度已编号。"""
        self._require_node(node_id)
        if dof not in range(6):
            raise ValueError("局部自由度编号必须是 0 到 5。")
        if self.nodes[node_id].dof_indices is None:
            self.number_dofs()
        return int(self.nodes[node_id].dof_indices[dof])

    def element_dofs(self, element: Frame3D) -> np.ndarray:
        """返回单元的 12 个整体自由度编号。"""
        self.number_dofs()
        return np.concatenate((element.start_node.dof_indices, element.end_node.dof_indices))

    def constrained_dof_values(self) -> dict[int, float]:
        """将 ``(节点号, 节点自由度)`` 约束转换为整体自由度编号。"""
        self.number_dofs()
        return {
            self.dof_index(node_id, dof): value
            for (node_id, dof), value in self.prescribed_dofs.items()
        }

    def local_member_equivalent_load(self, element_id: int) -> np.ndarray:
        """汇总一根杆件全部杆上荷载形成的局部一致等效节点荷载。"""
        self._require_element(element_id)
        element = self.elements[element_id]
        equivalent = np.zeros(12, dtype=float)
        for load in self.member_loads.get(element_id, []):
            if isinstance(load, UniformMemberLoad):
                equivalent += element.local_uniform_load(load.local_components)
            else:
                equivalent += element.local_point_load(load.position, load.local_components)
        return equivalent

    def global_member_equivalent_load(self, element_id: int) -> np.ndarray:
        """将该杆件局部一致等效节点荷载转换为总体坐标系。"""
        element = self.elements[element_id]
        return element.transformation.T @ self.local_member_equivalent_load(element_id)

    def global_self_weight_equivalent_load(self, element_id: int) -> np.ndarray:
        """返回一根杆的自重一致等效节点荷载（总体坐标）。"""
        self._require_element(element_id)
        element = self.elements[element_id]
        return element.transformation.T @ self.local_self_weight_equivalent_load(element_id)

    def local_self_weight_components(self, element_id: int) -> np.ndarray:
        """返回自重线荷载在该杆局部坐标的 ``[qx,qy,qz]``。"""
        self._require_element(element_id)
        if not self.self_weight_enabled:
            return np.zeros(3, dtype=float)
        element = self.elements[element_id]
        return element.rotation @ (element.material.density * element.section.area * self.gravity)

    def local_self_weight_equivalent_load(self, element_id: int) -> np.ndarray:
        """返回自重一致等效节点荷载（局部坐标）。"""
        self._require_element(element_id)
        element = self.elements[element_id]
        return element.local_uniform_load(self.local_self_weight_components(element_id))

    def local_assembly_equivalent_load(self, element_id: int) -> np.ndarray:
        """返回制造长度偏差引起的局部初应变等效节点荷载。"""
        self._require_element(element_id)
        element = self.elements[element_id]
        delta_length = self.element_length_deviations.get(element_id, 0.0)
        initial_strain = delta_length / element.length
        axial_force = element.material.elastic_modulus * element.section.area * initial_strain
        load = np.zeros(12, dtype=float)
        load[0], load[6] = -axial_force, axial_force
        return load

    def global_assembly_equivalent_load(self, element_id: int) -> np.ndarray:
        """返回制造长度偏差引起的总体坐标等效节点荷载。"""
        self._require_element(element_id)
        element = self.elements[element_id]
        return element.transformation.T @ self.local_assembly_equivalent_load(element_id)

    def total_self_weight(self) -> np.ndarray:
        """返回全部杆件自重合力（总体坐标），未启用时为零。"""
        if not self.self_weight_enabled:
            return np.zeros(3, dtype=float)
        return sum(
            (element.material.density * element.section.area * element.length * self.gravity
             for element in self.elements.values()),
            start=np.zeros(3, dtype=float),
        )

    def _require_node(self, node_id: int) -> None:
        if node_id not in self.nodes:
            raise ValueError(f"节点 {node_id} 不存在。")

    def _require_element(self, element_id: int) -> None:
        if element_id not in self.elements:
            raise ValueError(f"杆件 {element_id} 不存在。")
