"""空间刚架单元的局部坐标系和坐标变换。"""

from __future__ import annotations

import numpy as np


_PARALLEL_TOLERANCE = 1.0e-10


def local_axes(
    start: np.ndarray,
    end: np.ndarray,
    reference_vector: np.ndarray | None = None,
) -> np.ndarray:
    """建立从全局向量到局部向量的 3×3 旋转矩阵 R。

    R 的三行依次为局部 x、y、z 轴在全局坐标系中的方向余弦，因此
    ``v_local = R @ v_global``。局部 x 轴由起点指向终点。若用户没有
    给定截面朝向，则优先投影全局 Z 轴；当杆件近似平行 Z 轴时，自动改用
    全局 Y 轴，避免叉乘趋近于零。
    """
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    if start.shape != (3,) or end.shape != (3,):
        raise ValueError("杆件起、终点必须是长度为 3 的坐标向量。")

    chord = end - start
    length = np.linalg.norm(chord)
    if length <= _PARALLEL_TOLERANCE:
        raise ValueError("杆件长度必须大于零。")
    ex = chord / length

    if reference_vector is None:
        reference = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(ex, reference)) > 1.0 - _PARALLEL_TOLERANCE:
            reference = np.array([0.0, 1.0, 0.0])
    else:
        reference = np.asarray(reference_vector, dtype=float)
        if reference.shape != (3,):
            raise ValueError("局部朝向参考向量必须是长度为 3 的向量。")

    # 从参考向量中去除沿局部 x 的分量，使局部 y 与局部 x 正交。
    ey = reference - np.dot(reference, ex) * ex
    ey_norm = np.linalg.norm(ey)
    if ey_norm <= _PARALLEL_TOLERANCE:
        raise ValueError("局部朝向参考向量不能与杆件轴线平行。")
    ey /= ey_norm
    ez = np.cross(ex, ey)

    rotation = np.vstack((ex, ey, ez))
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-12):
        raise RuntimeError("局部坐标系构造失败，旋转矩阵不是正交矩阵。")
    return rotation


def transformation_matrix(rotation: np.ndarray) -> np.ndarray:
    """由 3×3 旋转矩阵生成节点 6 自由度的 12×12 变换矩阵 T。

    位移变换为 ``d_local = T @ d_global``，故刚度变换为
    ``K_global = T.T @ K_local @ T``。平动与转角均服从相同的方向余弦变换。
    """
    rotation = np.asarray(rotation, dtype=float)
    if rotation.shape != (3, 3):
        raise ValueError("旋转矩阵必须是 3×3 矩阵。")
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-12):
        raise ValueError("旋转矩阵必须是正交矩阵。")

    transform = np.zeros((12, 12), dtype=float)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform

