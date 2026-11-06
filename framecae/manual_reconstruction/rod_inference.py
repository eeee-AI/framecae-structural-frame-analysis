"""Rank possible straight rods between reconstructed nodes using all views."""

from __future__ import annotations

import base64
from itertools import combinations
import math

import cv2
import numpy as np

from .reconstruction import ReconstructionError, _scaled_intrinsics, load_calibration


def _decode_image(data_url: str) -> np.ndarray:
    if not isinstance(data_url, str) or not data_url.startswith("data:image/jpeg;base64,"):
        raise ReconstructionError("杆件识别需要浏览器压缩后的 JPEG 照片。")
    encoded = data_url.split(",", 1)[1]
    if len(encoded) > 9_000_000:
        raise ReconstructionError("单张分析图片过大，请缩小后再试。")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ReconstructionError("图片编码无效。") from exc
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.size == 0 or max(image.shape) > 2600:
        raise ReconstructionError("无法读取分析图片，或图片超过 2600 像素。")
    return image


def _detect_segments(gray: np.ndarray) -> np.ndarray:
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    # The original image preserves sharp edges; CLAHE helps low-contrast rods.
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    groups = []
    for image in (gray, enhanced):
        detected = detector.detect(image)[0]
        if detected is not None:
            groups.append(detected.reshape(-1, 4))
    if not groups:
        return np.empty((0, 4), dtype=np.float32)
    segments = np.vstack(groups)
    lengths = np.linalg.norm(segments[:, 2:4] - segments[:, :2], axis=1)
    segments = segments[lengths >= 10.0]
    if len(segments) > 6000:
        lengths = np.linalg.norm(segments[:, 2:4] - segments[:, :2], axis=1)
        segments = segments[np.argsort(lengths)[-6000:]]
    return segments.astype(np.float32)


def _score_projected_line(a: np.ndarray, b: np.ndarray,
                          segments: np.ndarray) -> dict:
    direction = b - a
    length = float(np.linalg.norm(direction))
    if length < 22.0 or not len(segments):
        return {"score": 0.0, "coverage": 0.0, "matched_segments": 0,
                "projected_length_px": round(length, 1)}
    along = direction / length
    normal = np.array([-along[1], along[0]])
    corridor = max(5.0, min(18.0, 0.018 * length))
    start, stop = 0.12 * length, 0.88 * length
    support = np.zeros(32, dtype=np.float32)
    matched = 0
    for segment in segments:
        p, q = segment[:2], segment[2:]
        vector = q - p
        segment_length = float(np.linalg.norm(vector))
        if segment_length < 10:
            continue
        alignment = abs(float(np.dot(vector / segment_length, along)))
        if alignment < 0.94:
            continue
        tp, tq = float(np.dot(p - a, along)), float(np.dot(q - a, along))
        low, high = max(start, min(tp, tq)), min(stop, max(tp, tq))
        if high - low < max(6.0, 0.035 * length):
            continue
        perpendicular = max(abs(float(np.dot(p - a, normal))),
                            abs(float(np.dot(q - a, normal))))
        if perpendicular > corridor:
            continue
        closeness = math.exp(-0.5 * (perpendicular / corridor) ** 2)
        weight = closeness * alignment ** 4
        first = max(0, int((low - start) / (stop - start) * 32))
        last = min(32, int(math.ceil((high - start) / (stop - start) * 32)))
        support[first:last] = np.maximum(support[first:last], weight)
        matched += 1
    coverage = float(np.mean(support >= 0.35))
    score = 0.7 * coverage + 0.3 * float(np.mean(support))
    return {"score": round(score, 4), "coverage": round(coverage, 4),
            "matched_segments": matched, "projected_length_px": round(length, 1)}


def _project_samples(a: np.ndarray, b: np.ndarray, R: np.ndarray,
                     t: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray | None:
    samples = np.linspace(0, 1, 9)[:, None] * (b - a) + a
    camera_xyz = (R @ samples.T).T + t
    if np.any(camera_xyz[:, 2] <= 0):
        return None
    rvec, _ = cv2.Rodrigues(R)
    projected, _ = cv2.projectPoints(samples, rvec, t, K, dist)
    return projected.reshape(-1, 2)


def _intermediate_node(a: np.ndarray, b: np.ndarray,
                       all_points: list[dict], excluded: set[str]) -> str | None:
    vector = b - a
    length2 = float(np.dot(vector, vector))
    if length2 < 1e-12:
        return None
    for point in all_points:
        if point["id"] in excluded:
            continue
        xyz = np.asarray(point["xyz"], dtype=np.float64)
        fraction = float(np.dot(xyz - a, vector) / length2)
        if 0.1 < fraction < 0.9:
            distance = float(np.linalg.norm(xyz - (a + fraction * vector)))
            if distance < 0.035 * math.sqrt(length2):
                return point["id"]
    return None


def infer_rods(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ReconstructionError("杆件识别请求格式无效。")
    views = payload.get("views")
    reconstruction = payload.get("reconstruction")
    if not isinstance(views, list) or not 2 <= len(views) <= 4 or not isinstance(reconstruction, dict):
        raise ReconstructionError("请先上传 2–4 张照片并完成节点三维重建。")
    raw_points = reconstruction.get("points")
    raw_cameras = reconstruction.get("cameras")
    if not isinstance(raw_points, list) or not 2 <= len(raw_points) <= 20:
        raise ReconstructionError("需要 2–20 个已重建节点。")
    if not isinstance(raw_cameras, list) or len(raw_cameras) != len(views):
        raise ReconstructionError("相机位姿与照片数量不一致。")

    calibration = load_calibration()
    distortion = np.asarray(calibration["distortion"], dtype=np.float64)
    points = []
    for raw in raw_points:
        xyz = np.asarray(raw.get("xyz"), dtype=np.float64).reshape(3)
        if not np.all(np.isfinite(xyz)):
            raise ReconstructionError("节点坐标无效。")
        points.append({"id": str(raw["id"]), "label": str(raw.get("label", raw["id"])),
                       "xyz": xyz})
    cameras = []
    images = []
    intrinsics_small = []
    intrinsics_original = []
    segments_by_view = []
    for view, camera in zip(views, raw_cameras):
        image = _decode_image(view.get("image_data_url"))
        h, w = image.shape
        original_width, original_height = int(view["width"]), int(view["height"])
        if abs(w / h - original_width / original_height) > 0.015 * original_width / original_height:
            raise ReconstructionError("分析图片与原照片的宽高比不一致。")
        K_small = _scaled_intrinsics(w, h, calibration)
        K_original = _scaled_intrinsics(original_width, original_height, calibration)
        R = np.asarray(camera["R_world_to_camera"], dtype=np.float64).reshape(3, 3)
        t = np.asarray(camera["t_world_to_camera"], dtype=np.float64).reshape(3)
        if not np.all(np.isfinite(R)) or not np.all(np.isfinite(t)):
            raise ReconstructionError("相机位姿无效。")
        images.append(image)
        intrinsics_small.append(K_small)
        intrinsics_original.append(K_original)
        cameras.append((R, t))
        segments_by_view.append(_detect_segments(image))

    candidates = []
    for first, second in combinations(points, 2):
        a, b = first["xyz"], second["xyz"]
        length = float(np.linalg.norm(b - a))
        if length < 1e-9:
            continue
        blocker = _intermediate_node(a, b, points, {first["id"], second["id"]})
        evidence = []
        projections = []
        for view_index, ((R, t), image) in enumerate(zip(cameras, images)):
            small = _project_samples(a, b, R, t, intrinsics_small[view_index], distortion)
            original = _project_samples(a, b, R, t, intrinsics_original[view_index], distortion)
            if small is None or original is None:
                evidence.append({"score": 0.0, "coverage": 0.0, "matched_segments": 0,
                                 "projected_length_px": 0.0})
                projections.append(None)
                continue
            h, w = image.shape
            if np.any(small[:, 0] < 0) or np.any(small[:, 0] >= w) or \
               np.any(small[:, 1] < 0) or np.any(small[:, 1] >= h):
                evidence.append({"score": 0.0, "coverage": 0.0, "matched_segments": 0,
                                 "projected_length_px": 0.0})
                projections.append(None)
                continue
            evidence.append(_score_projected_line(small[0], small[-1],
                                                  segments_by_view[view_index]))
            projections.append(np.round(original, 2).tolist())
        ranked = sorted((item["score"] for item in evidence), reverse=True)
        combined = float(np.mean(ranked[:2]))
        support_views = sum(item["score"] >= 0.55 and item["coverage"] >= 0.48
                            for item in evidence)
        if blocker:
            status = "review" if combined >= 0.35 else "unlikely"
        elif combined >= 0.65 and support_views >= 2:
            status = "suggested"
        elif combined >= 0.35 or max(ranked) >= 0.65:
            status = "review"
        else:
            status = "unlikely"
        candidates.append({
            "id": f"{first['id']}:{second['id']}", "a": first["id"], "b": second["id"],
            "label_a": first["label"], "label_b": second["label"],
            "length": length, "score": round(combined, 4),
            "support_views": support_views, "status": status,
            "intermediate_node": blocker, "evidence": evidence,
            "projections": projections,
        })
    candidates.sort(key=lambda item: (-item["score"], item["id"]))
    return {"unit": reconstruction.get("unit", "relative"),
            "candidates": candidates,
            "suggested_count": sum(item["status"] == "suggested" for item in candidates),
            "review_count": sum(item["status"] == "review" for item in candidates),
            "image_segment_counts": [len(item) for item in segments_by_view],
            "method": "projected multi-view LSD line support; suggestions require at least two supporting views"}

