"""空间刚架计算结果的 Matplotlib 三维绘图。"""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib import colormaps
from matplotlib.axes import Axes
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from framecae.core.model import Model
from framecae.solver.static_solver import StaticResult


def plot_frame_result(
    figure: Figure,
    model: Model,
    result: StaticResult,
    deformation_scale: float = 1.0,
    show_node_labels: bool = True,
    show_element_labels: bool = False,
) -> Axes:
    """在给定 Figure 中绘制原始构形和按位移模着色的变形构形。

    原始杆件为浅灰虚线；变形后的杆件以节点平动位移模值着色。三维坐标轴
    支持用户在 Matplotlib 工具栏中拖动旋转、滚轮缩放及平移。
    """
    figure.clear()
    axes = figure.add_subplot(111, projection="3d")
    node_ids = sorted(model.nodes)
    coordinates = np.array([model.nodes[node_id].coordinates for node_id in node_ids])
    translations = np.array(
        [result.node_displacement(model, node_id)[:3] for node_id in node_ids]
    )
    displacement_magnitude = np.linalg.norm(translations, axis=1)
    deformed_coordinates = coordinates + deformation_scale * translations
    node_index = {node_id: position for position, node_id in enumerate(node_ids)}

    maximum = float(displacement_magnitude.max())
    normalizer = Normalize(vmin=0.0, vmax=maximum if maximum > 0.0 else 1.0)
    colour_map = colormaps["plasma"]

    for element in model.elements.values():
        first_index = node_index[element.start_node.id]
        second_index = node_index[element.end_node.id]
        original = coordinates[[first_index, second_index]]
        deformed = deformed_coordinates[[first_index, second_index]]
        average_displacement = 0.5 * (
            displacement_magnitude[first_index] + displacement_magnitude[second_index]
        )
        axes.plot(
            original[:, 0], original[:, 1], original[:, 2],
            color="#96a0ad", linestyle="--", linewidth=1.0, alpha=0.85,
        )
        axes.plot(
            deformed[:, 0], deformed[:, 1], deformed[:, 2],
            color=colour_map(normalizer(average_displacement)), linewidth=3.0,
        )
        if show_element_labels:
            midpoint = deformed.mean(axis=0)
            axes.text(*midpoint, f"E{element.id}", color="#28323c", fontsize=8)

    scatter = axes.scatter(
        deformed_coordinates[:, 0], deformed_coordinates[:, 1], deformed_coordinates[:, 2],
        c=displacement_magnitude, cmap=colour_map, norm=normalizer,
        s=28, edgecolors="#20252b", linewidths=0.35, depthshade=False,
    )
    if show_node_labels:
        offset = _label_offset(coordinates, deformed_coordinates)
        for position, node_id in enumerate(node_ids):
            axes.text(
                *(deformed_coordinates[position] + offset), f"N{node_id}",
                color="#111827", fontsize=8,
            )

    colour_bar = figure.colorbar(scatter, ax=axes, shrink=0.66, pad=0.08)
    colour_bar.set_label("节点平动位移模值 |u| (m)")
    axes.set_title(f"空间刚架：原始构形（灰虚线）与变形构形（放大 {deformation_scale:g} 倍）", pad=18)
    axes.set_xlabel("全局 X (m)")
    axes.set_ylabel("全局 Y (m)")
    axes.set_zlabel("全局 Z (m)")
    axes.grid(True, alpha=0.25)
    _set_equal_aspect(axes, np.vstack((coordinates, deformed_coordinates)))
    figure.tight_layout()
    return axes


def _label_offset(coordinates: np.ndarray, deformed_coordinates: np.ndarray) -> np.ndarray:
    span = np.ptp(np.vstack((coordinates, deformed_coordinates)), axis=0)
    characteristic_span = max(float(span.max()), 1.0)
    return np.full(3, 0.018 * characteristic_span)


def _set_equal_aspect(axes: Axes, points: np.ndarray) -> None:
    """为三维图设置相同比例，避免结构在视觉上被拉伸。"""
    lower = points.min(axis=0)
    upper = points.max(axis=0)
    center = 0.5 * (lower + upper)
    radius = max(float((upper - lower).max()) * 0.55, 0.5)
    axes.set_xlim(center[0] - radius, center[0] + radius)
    axes.set_ylim(center[1] - radius, center[1] + radius)
    axes.set_zlim(center[2] - radius, center[2] + radius)
    axes.set_box_aspect((1.0, 1.0, 1.0))
