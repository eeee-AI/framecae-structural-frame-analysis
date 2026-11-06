"""由整体梁模型结果识别需要局部实体分析的危险节点。"""

from __future__ import annotations

from dataclasses import dataclass

from framecae.core.model import Model
from framecae.postprocess.internal_force import evaluate_section, sample_element_sections
from framecae.solver.static_solver import StaticResult


@dataclass(frozen=True)
class CriticalNode:
    """按相邻杆端名义应力排序的危险节点。"""

    node_id: int
    nominal_stress: float
    connected_elements: tuple[int, ...]


@dataclass(frozen=True)
class CriticalSection:
    """杆件任意截面处的危险名义应力位置。"""

    element_id: int
    position: float
    nominal_stress: float


def rank_critical_nodes(model: Model, result: StaticResult) -> list[CriticalNode]:
    """对全部节点按相邻单元端部最大名义应力绝对值降序排序。"""
    records: list[CriticalNode] = []
    for node_id in sorted(model.nodes):
        connected: list[int] = []
        maximum = 0.0
        for element_id, element in model.elements.items():
            if element.start_node.id == node_id:
                connected.append(element_id)
                maximum = max(maximum, abs(evaluate_section(model, result, element_id, 0.0).nominal_stress))
            elif element.end_node.id == node_id:
                connected.append(element_id)
                maximum = max(maximum, abs(evaluate_section(model, result, element_id, element.length).nominal_stress))
        records.append(CriticalNode(node_id, maximum, tuple(connected)))
    return sorted(records, key=lambda record: record.nominal_stress, reverse=True)


def rank_critical_sections(model: Model, result: StaticResult) -> list[CriticalSection]:
    """对全部杆件的端部、荷载突变点和应力驻点按名义应力排序。"""
    records = [
        CriticalSection(element_id, station.position, station.nominal_stress)
        for element_id in model.elements
        for station in sample_element_sections(model, result, element_id)
    ]
    return sorted(records, key=lambda record: abs(record.nominal_stress), reverse=True)
