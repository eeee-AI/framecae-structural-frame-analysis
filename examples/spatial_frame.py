"""三维可视化界面使用的空间刚架算例。"""

from __future__ import annotations

import math

from framecae.core.material import Material
from framecae.core.model import Model
from framecae.core.node import Node
from framecae.core.section import Section
from framecae.elements.frame3d import Frame3D


def build_space_frame() -> Model:
    """建立四柱两层空间刚架，供三维结果展示与后续功能调试使用。"""
    steel = Material(1, elastic_modulus=210.0e9, poisson_ratio=0.30, thermal_expansion=1.2e-5)
    # 01 与 03 共用 D、A 确定的圆管截面，不能把方管等效惯性传给圆管实体。
    radius, area = .08, .0075
    inner_squared = radius**2-area/math.pi
    inertia = math.pi*(radius**4-inner_squared**2)/4
    section = Section(1, area=area, iy=inertia, iz=inertia, torsion_constant=2*inertia, characteristic_size=2*radius)
    model = Model()
    coordinates = {
        1: (0.0, 0.0, 0.0), 2: (4.0, 0.0, 0.0), 3: (4.0, 3.0, 0.0), 4: (0.0, 3.0, 0.0),
        5: (0.0, 0.0, 3.0), 6: (4.0, 0.0, 3.0), 7: (4.0, 3.0, 3.0), 8: (0.0, 3.0, 3.0),
    }
    for node_id, coordinate in coordinates.items():
        model.add_node(Node(node_id, *coordinate))

    connectivity = (
        (1, 2), (2, 3), (3, 4), (4, 1),
        (5, 6), (6, 7), (7, 8), (8, 5),
        (1, 5), (2, 6), (3, 7), (4, 8),
    )
    for element_id, (start_id, end_id) in enumerate(connectivity, start=1):
        model.add_element(
            Frame3D(element_id, model.nodes[start_id], model.nodes[end_id], steel, section)
        )

    for node_id in (1, 2, 3, 4):
        model.fix_node(node_id)
    for node_id in (5, 6, 7, 8):
        model.add_nodal_load(node_id, [7_500.0, 0.0, -35_000.0, 0.0, 0.0, 0.0])
    return model
