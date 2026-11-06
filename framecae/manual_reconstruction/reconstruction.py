"""Sparse 2-4 view reconstruction from manually matched image points."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix


CALIBRATION = Path(__file__).resolve().parent / "you_chessboard_calibration.json"


class ReconstructionError(ValueError):
    pass


def load_calibration() -> dict:
    import json

    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return {
        "image_size_px": data["image_size_px"],
        "K": data["camera_matrix_K"],
        "distortion": data["distortion_coefficients_k1_k2_p1_p2_k3"],
        "calibration_rms_px": data["overall_rms_px"],
    }


def _scaled_intrinsics(width: int, height: int, calibration: dict) -> np.ndarray:
    base_width, base_height = calibration["image_size_px"]
    if abs(width / height - base_width / base_height) > 0.01 * base_width / base_height:
        raise ReconstructionError(
            f"图片尺寸 {width}×{height} 与标定图 {base_width}×{base_height} 的比例不同；"
            "请上传未经裁剪的同一相机照片。"
        )
    K = np.asarray(calibration["K"], dtype=np.float64).copy()
    K[0, :] *= width / base_width
    K[1, :] *= height / base_height
    return K


def _undistort(points: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    return cv2.undistortPoints(points.reshape(-1, 1, 2), K, dist).reshape(-1, 2)


def _triangulate_pair(
    pixel_a: np.ndarray, pixel_b: np.ndarray,
    pose_a: tuple[np.ndarray, np.ndarray], pose_b: tuple[np.ndarray, np.ndarray],
    K_a: np.ndarray, K_b: np.ndarray, dist: np.ndarray,
) -> np.ndarray | None:
    R_a, t_a = pose_a
    R_b, t_b = pose_b
    p_a = _undistort(pixel_a.reshape(1, 2), K_a, dist).T
    p_b = _undistort(pixel_b.reshape(1, 2), K_b, dist).T
    P_a = np.column_stack((R_a, t_a))
    P_b = np.column_stack((R_b, t_b))
    homogeneous = cv2.triangulatePoints(P_a, P_b, p_a, p_b).reshape(4)
    if abs(homogeneous[3]) < 1e-12:
        return None
    xyz = homogeneous[:3] / homogeneous[3]
    if not np.all(np.isfinite(xyz)):
        return None
    if (R_a @ xyz + t_a)[2] <= 0 or (R_b @ xyz + t_b)[2] <= 0:
        return None
    return xyz


def _project(xyz: np.ndarray, pose: tuple[np.ndarray, np.ndarray],
             K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    R, t = pose
    rvec, _ = cv2.Rodrigues(R)
    projected, _ = cv2.projectPoints(xyz.reshape(-1, 1, 3), rvec, t, K, dist)
    return projected.reshape(-1, 2)


def _initial_two_view_pose(p0: np.ndarray, p1: np.ndarray,
                           K0: np.ndarray, K1: np.ndarray,
                           dist: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Try calibrated epipolar and planar models; select a cheiral low-error pose."""
    u0 = _undistort(p0, K0, dist)
    u1 = _undistort(p1, K1, dist)
    threshold = 6.0 / float(np.mean([K0[0, 0], K1[0, 0]]))
    candidates = []

    for method in (cv2.RANSAC, cv2.LMEDS):
        E, _ = cv2.findEssentialMat(u0, u1, focal=1.0, pp=(0.0, 0.0),
                                    method=method, prob=0.999,
                                    threshold=threshold)
        if E is None:
            continue
        for start in range(0, E.shape[0], 3):
            candidate = E[start:start + 3]
            if candidate.shape != (3, 3):
                continue
            try:
                _, R, t, _ = cv2.recoverPose(candidate, u0, u1, focal=1.0,
                                             pp=(0.0, 0.0))
                candidates.append((R, t.reshape(3)))
            except cv2.error:
                continue

    # Seven structural nodes are often coplanar. A homography gives another
    # valid initialization when the five-point essential fit is degenerate.
    for method in (0, cv2.RANSAC):
        H, _ = cv2.findHomography(u0, u1, method,
                                  ransacReprojThreshold=threshold)
        if H is None:
            continue
        try:
            _, rotations, translations, _ = cv2.decomposeHomographyMat(
                H, np.eye(3, dtype=np.float64))
        except cv2.error:
            continue
        for R, t in zip(rotations, translations):
            direction = t.reshape(3)
            length = float(np.linalg.norm(direction))
            if length > 1e-12:
                candidates.append((R, direction / length))

    scored = []
    origin = (np.eye(3), np.zeros(3))
    for R, t in candidates:
        second = (R, t)
        valid = []
        errors = []
        for index in range(len(p0)):
            xyz = _triangulate_pair(p0[index], p1[index], origin, second,
                                    K0, K1, dist)
            if xyz is None:
                continue
            prediction0 = _project(xyz, origin, K0, dist)[0]
            prediction1 = _project(xyz, second, K1, dist)[0]
            error = float(np.sqrt((np.sum((prediction0 - p0[index]) ** 2) +
                                   np.sum((prediction1 - p1[index]) ** 2)) / 2))
            if error < 12.0:
                valid.append(index)
                errors.append(error)
        if len(valid) >= 6:
            # Favour using all seven nodes while still rejecting a pose that
            # fits the observations poorly.
            score = float(np.median(errors)) + 5.0 * (len(p0) - len(valid))
            scored.append((score, -len(valid), R, t, valid))
    if not scored:
        raise ReconstructionError(
            "有效对应点不足，或前两张照片视差太小；请检查 7 个节点的标注。"
        )
    _, _, R, t, valid = min(scored, key=lambda item: (item[0], item[1]))
    return R, t, valid


def _triangulate_track(track: dict, poses: dict[int, tuple[np.ndarray, np.ndarray]],
                       intrinsics: list[np.ndarray], dist: np.ndarray) -> np.ndarray | None:
    views = [i for i in track["observations"] if i in poses]
    if len(views) < 2:
        return None
    candidates = []
    for a_index, a in enumerate(views):
        for b in views[a_index + 1:]:
            point = _triangulate_pair(track["observations"][a], track["observations"][b],
                                      poses[a], poses[b], intrinsics[a], intrinsics[b], dist)
            if point is None:
                continue
            errors = []
            positive = True
            for view in views:
                R, t = poses[view]
                if (R @ point + t)[2] <= 0:
                    positive = False
                    break
                predicted = _project(point, poses[view], intrinsics[view], dist)[0]
                errors.append(np.linalg.norm(predicted - track["observations"][view]))
            if positive:
                candidates.append((float(np.mean(np.square(errors))), point))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _parse_request(payload: dict, calibration: dict):
    if not isinstance(payload, dict):
        raise ReconstructionError("请求格式不正确。")
    views = payload.get("views")
    raw_tracks = payload.get("tracks")
    if not isinstance(views, list) or not 2 <= len(views) <= 4:
        raise ReconstructionError("请上传 2–4 张同一场景的照片。")
    if not isinstance(raw_tracks, list) or not 7 <= len(raw_tracks) <= 100:
        raise ReconstructionError("请标注至少 7 组、最多 100 组对应点。")

    intrinsics = []
    for view in views:
        if not isinstance(view, dict):
            raise ReconstructionError("图片信息无效。")
        width, height = view.get("width"), view.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width < 10 or height < 10:
            raise ReconstructionError("图片尺寸无效。")
        intrinsics.append(_scaled_intrinsics(width, height, calibration))

    tracks = []
    seen_ids = set()
    for raw in raw_tracks:
        if not isinstance(raw, dict):
            raise ReconstructionError("对应点格式无效。")
        track_id = str(raw.get("id", ""))
        if not track_id or track_id in seen_ids:
            raise ReconstructionError("对应点编号缺失或重复。")
        seen_ids.add(track_id)
        observations = {}
        for key, xy in raw.get("observations", {}).items():
            try:
                index = int(key)
                point = np.asarray(xy, dtype=np.float64).reshape(2)
            except (ValueError, TypeError) as exc:
                raise ReconstructionError(f"点 {track_id} 的坐标无效。") from exc
            if index < 0 or index >= len(views) or not np.all(np.isfinite(point)):
                raise ReconstructionError(f"点 {track_id} 的坐标无效。")
            if not (0 <= point[0] < views[index]["width"] and
                    0 <= point[1] < views[index]["height"]):
                raise ReconstructionError(f"点 {track_id} 超出了第 {index + 1} 张图片。")
            observations[index] = point
        if len(observations) >= 2:
            tracks.append({"id": track_id, "label": str(raw.get("label", track_id))[:80],
                           "observations": observations})
    return views, tracks, intrinsics


def _bundle_adjust(
    poses: dict[int, tuple[np.ndarray, np.ndarray]], points: dict[str, np.ndarray],
    tracks: list[dict], intrinsics: list[np.ndarray], dist: np.ndarray,
) -> tuple[dict[int, tuple[np.ndarray, np.ndarray]], dict[str, np.ndarray], dict]:
    point_ids = list(points)
    point_index = {name: i for i, name in enumerate(point_ids)}
    observations = [
        (view, point_index[track["id"]], xy)
        for track in tracks if track["id"] in point_index
        for view, xy in track["observations"].items() if view in poses
    ]
    view_count = len(poses)
    pose_param_count = 5 + 6 * (view_count - 2)
    t1 = poses[1][1]
    azimuth = math.atan2(t1[1], t1[0])
    elevation = math.atan2(t1[2], math.hypot(t1[0], t1[1]))
    r1, _ = cv2.Rodrigues(poses[1][0])
    chunks = [r1.reshape(3), np.array([azimuth, elevation])]
    for view in range(2, view_count):
        rvec, _ = cv2.Rodrigues(poses[view][0])
        chunks.extend([rvec.reshape(3), poses[view][1].reshape(3)])
    chunks.extend(points[name].reshape(3) for name in point_ids)
    initial = np.concatenate(chunks)

    def unpack(params: np.ndarray):
        new_poses = {0: (np.eye(3), np.zeros(3))}
        R1, _ = cv2.Rodrigues(params[:3])
        az, el = params[3:5]
        t1_unit = np.array([math.cos(el) * math.cos(az),
                            math.cos(el) * math.sin(az), math.sin(el)])
        new_poses[1] = (R1, t1_unit)
        offset = 5
        for view in range(2, view_count):
            rotation, _ = cv2.Rodrigues(params[offset:offset + 3])
            new_poses[view] = (rotation, params[offset + 3:offset + 6])
            offset += 6
        new_points = params[pose_param_count:].reshape(-1, 3)
        return new_poses, new_points

    def residuals(params: np.ndarray) -> np.ndarray:
        current_poses, current_points = unpack(params)
        result = np.empty((len(observations), 2), dtype=np.float64)
        for view in range(view_count):
            indices = [j for j, item in enumerate(observations) if item[0] == view]
            if not indices:
                continue
            xyz = current_points[[observations[j][1] for j in indices]]
            projected = _project(xyz, current_poses[view], intrinsics[view], dist)
            measured = np.array([observations[j][2] for j in indices])
            result[indices] = projected - measured
        return result.ravel()

    sparsity = lil_matrix((2 * len(observations), len(initial)), dtype=np.int8)
    for obs_index, (view, p_index, _) in enumerate(observations):
        if view == 1:
            sparsity[2 * obs_index:2 * obs_index + 2, 0:5] = 1
        elif view >= 2:
            start = 5 + 6 * (view - 2)
            sparsity[2 * obs_index:2 * obs_index + 2, start:start + 6] = 1
        start = pose_param_count + 3 * p_index
        sparsity[2 * obs_index:2 * obs_index + 2, start:start + 3] = 1

    fit = least_squares(residuals, initial, jac_sparsity=sparsity.tocsr(),
                        loss="soft_l1", f_scale=2.0, max_nfev=100,
                        ftol=1e-7, xtol=1e-7)
    fitted_poses, fitted_points = unpack(fit.x)
    fitted_points = {name: fitted_points[i] for i, name in enumerate(point_ids)}
    residual_xy = residuals(fit.x).reshape(-1, 2)
    errors = np.linalg.norm(residual_xy, axis=1)
    diagnostics = {"overall_rmse_px": float(np.sqrt(np.mean(errors ** 2))),
                   "optimization_iterations": int(fit.nfev),
                   "per_view_rmse_px": {}, "per_point_rmse_px": {}}
    for view in range(view_count):
        selected = [errors[i] for i, obs in enumerate(observations) if obs[0] == view]
        diagnostics["per_view_rmse_px"][str(view)] = float(np.sqrt(np.mean(np.square(selected))))
    for name, index in point_index.items():
        selected = [errors[i] for i, obs in enumerate(observations) if obs[1] == index]
        diagnostics["per_point_rmse_px"][name] = float(np.sqrt(np.mean(np.square(selected))))
    return fitted_poses, fitted_points, diagnostics


def reconstruct(payload: dict) -> dict:
    calibration = load_calibration()
    views, tracks, intrinsics = _parse_request(payload, calibration)
    dist = np.asarray(calibration["distortion"], dtype=np.float64)
    first_pair = [track for track in tracks if 0 in track["observations"] and
                  1 in track["observations"]]
    if len(first_pair) < 7:
        raise ReconstructionError("前两张照片需要全部 7 组共同对应点。")
    p0 = np.array([track["observations"][0] for track in first_pair])
    p1 = np.array([track["observations"][1] for track in first_pair])
    R, t, valid_indices = _initial_two_view_pose(p0, p1, intrinsics[0],
                                                  intrinsics[1], dist)
    poses = {0: (np.eye(3), np.zeros(3)), 1: (R, t)}
    inlier_ids = {first_pair[index]["id"] for index in valid_indices}
    points = {}
    for track in first_pair:
        if track["id"] in inlier_ids:
            xyz = _triangulate_track(track, poses, intrinsics, dist)
            if xyz is not None:
                points[track["id"]] = xyz
    if len(points) < 6:
        raise ReconstructionError("可三角化的点不足；请检查标注和两张照片的视差。")

    for view in range(2, len(views)):
        known = [(points[track["id"]], track["observations"][view])
                 for track in tracks if track["id"] in points and view in track["observations"]]
        if len(known) < 6:
            raise ReconstructionError(
                f"第 {view + 1} 张照片至少需要 6 个已在前面照片重建出的点；"
                "请给这些点补充该照片上的标注。"
            )
        object_xyz = np.asarray([item[0] for item in known], dtype=np.float64)
        image_xy = np.asarray([item[1] for item in known], dtype=np.float64)
        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            object_xyz, image_xy, intrinsics[view], dist,
            iterationsCount=2000, reprojectionError=10.0, confidence=0.999,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if success and inliers is not None and len(inliers) >= 6:
            refine_xyz = object_xyz[inliers[:, 0]]
            refine_xy = image_xy[inliers[:, 0]]
        else:
            # Seven manually selected nodes may all be valid while their
            # initial triangulation is noisy. Try the complete set, then
            # accept it only if the image residual remains reasonable.
            success, rvec, tvec = cv2.solvePnP(
                object_xyz, image_xy, intrinsics[view], dist,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not success:
                raise ReconstructionError(f"第 {view + 1} 张照片的相机位姿求解失败；请检查对应点。")
            refine_xyz, refine_xy = object_xyz, image_xy
        rvec, tvec = cv2.solvePnPRefineLM(refine_xyz, refine_xy,
                                           intrinsics[view], dist, rvec, tvec)
        projected, _ = cv2.projectPoints(refine_xyz, rvec, tvec, intrinsics[view], dist)
        pose_rmse = float(np.sqrt(np.mean(np.sum(
            (projected.reshape(-1, 2) - refine_xy) ** 2, axis=1))))
        if pose_rmse > 10.0:
            raise ReconstructionError(
                f"第 {view + 1} 张照片的位姿误差为 {pose_rmse:.1f} 像素；请检查对应点。"
            )
        rotation, _ = cv2.Rodrigues(rvec)
        poses[view] = (rotation, tvec.reshape(3))
        for track in tracks:
            if track["id"] not in points and len([v for v in track["observations"] if v in poses]) >= 2:
                xyz = _triangulate_track(track, poses, intrinsics, dist)
                if xyz is not None:
                    points[track["id"]] = xyz

    poses, points, diagnostics = _bundle_adjust(poses, points, tracks, intrinsics, dist)
    scale = payload.get("scale")
    unit = "relative"
    scale_factor = 1.0
    if scale:
        a, b = str(scale.get("point_a", "")), str(scale.get("point_b", ""))
        try:
            distance_mm = float(scale.get("distance_mm"))
        except (TypeError, ValueError) as exc:
            raise ReconstructionError("已知距离必须是大于 0 的毫米数。") from exc
        if a == b or a not in points or b not in points or not math.isfinite(distance_mm) or distance_mm <= 0:
            raise ReconstructionError("请选择两个已重建的不同点，并输入有效的已知距离。")
        raw_distance = float(np.linalg.norm(points[a] - points[b]))
        if raw_distance < 1e-9:
            raise ReconstructionError("所选两点的重建距离接近 0，无法确定尺寸。")
        scale_factor = distance_mm / raw_distance
        unit = "mm"

    result_points = []
    for track in tracks:
        if track["id"] not in points:
            continue
        result_points.append({
            "id": track["id"], "label": track["label"],
            "xyz": (points[track["id"]] * scale_factor).tolist(),
            "observed_views": sorted(track["observations"]),
            "rmse_px": diagnostics["per_point_rmse_px"][track["id"]],
        })
    result_cameras = []
    for view in range(len(views)):
        R, t = poses[view]
        center = -R.T @ t
        result_cameras.append({"view_index": view, "name": views[view].get("name", f"View {view + 1}"),
                               "center": (center * scale_factor).tolist(),
                               "R_world_to_camera": R.tolist(),
                               "t_world_to_camera": (t * scale_factor).tolist()})

    warnings = []
    if unit == "relative":
        warnings.append("未提供已知距离，坐标只有相对尺度；第一、二相机中心距离定义为 1。")
    if diagnostics["overall_rmse_px"] > 3.0:
        warnings.append("重投影误差超过 3 像素，请检查错配、模糊点或相机标定。")
    if len(points) < len(tracks):
        warnings.append(f"{len(tracks) - len(points)} 组点未通过几何检查，未进入点云。")
    return {
        "unit": unit, "scale_factor": scale_factor,
        "points": result_points, "cameras": result_cameras,
        "overall_rmse_px": diagnostics["overall_rmse_px"],
        "per_view_rmse_px": diagnostics["per_view_rmse_px"],
        "baseline_inliers": len(inlier_ids), "baseline_matches": len(first_pair),
        "optimization_iterations": diagnostics["optimization_iterations"],
        "warnings": warnings,
    }

