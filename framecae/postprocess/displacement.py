"""Continuous centreline recovery for the existing linear Euler-Bernoulli model.

No stiffness, nodal solution or local-solid boundary mapping is changed.
Each interval uses t=(x-x0)/(x1-x0) and ascending vector coefficients in metres.
Nodal loads give cubics, transverse uniform loads quartics, point loads splits.
"""
from __future__ import annotations

from math import comb
import numpy as np

from framecae.core.member_load import PointMemberLoad, UniformMemberLoad
from framecae.core.model import Model
from framecae.solver.static_solver import StaticResult


def _restrict(coefficients: np.ndarray, lower: float, width: float) -> np.ndarray:
    """Substitute s=lower+width*t in an ascending vector polynomial."""
    output = np.zeros_like(coefficients)
    for power in range(len(coefficients)):
        for order in range(power + 1):
            output[order] += coefficients[power] * comb(power, order) * lower**(power-order) * width**order
    return output


def polynomial_value(coefficients, parameter: float) -> np.ndarray:
    value = np.zeros(3)
    for coefficient in reversed(coefficients):
        value = value * parameter + coefficient
    return value


def curve_peak(segments: list[dict]) -> dict:
    """Numerical maximum of |u| from endpoints and stationary points of |u|².

    Floating-point polynomial roots, not an exact-arithmetic certificate or a
    display-grid maximum. Scaling protects the degree-seven root problem.
    """
    best = {"magnitude": -1.0, "position": 0.0, "displacement": [0.0, 0.0, 0.0]}
    for segment in segments:
        coefficients = np.asarray(segment["displacementCoefficients"])
        scale = float(np.max(np.abs(coefficients)))
        candidates = [0.0, 1.0]
        if scale > 0:
            normalized = coefficients / scale
            squared = np.zeros(9)
            for axis in range(3):
                product = np.polynomial.polynomial.polymul(normalized[:, axis], normalized[:, axis])
                squared[:len(product)] += product
            derivative = np.polynomial.polynomial.polyder(squared)
            derivative_scale = float(np.max(np.abs(derivative)))
            if derivative_scale > 0:
                for root in np.polynomial.polynomial.polyroots(derivative / derivative_scale):
                    if abs(root.imag) <= 1e-7 and -1e-10 <= root.real <= 1 + 1e-10:
                        candidates.append(float(np.clip(root.real, 0, 1)))
        for parameter in candidates:
            displacement = polynomial_value(coefficients, parameter)
            magnitude = float(np.linalg.norm(displacement))
            if magnitude > best["magnitude"]:
                best = {"magnitude": magnitude,
                        "position": segment["x0"] + parameter * (segment["x1"] - segment["x0"]),
                        "displacement": displacement.tolist()}
    return best


def build_element_curve(model: Model, result: StaticResult, element_id: int) -> dict:
    element = model.elements[element_id]
    length = element.length
    local = element.transformation @ result.displacements[model.element_dofs(element)]
    n1 = np.array([1., 0., -3., 2., 0.])
    n2 = length * np.array([0., 1., -2., 1., 0.])
    n3 = np.array([0., 0., 3., -2., 0.])
    n4 = length * np.array([0., 0., -1., 1., 0.])
    coefficients = np.column_stack((
        np.array([local[0], local[6]-local[0], 0., 0., 0.]),
        n1*local[1] + n2*local[5] + n3*local[7] + n4*local[11],
        n1*local[2] - n2*local[4] + n3*local[8] - n4*local[10],
    ))
    ea = element.material.elastic_modulus * element.section.area
    ei = element.material.elastic_modulus * np.array([element.section.iz, element.section.iy])
    uniform = model.local_self_weight_components(element_id).copy()
    point_loads = []
    for load in model.member_loads.get(element_id, []):
        if isinstance(load, UniformMemberLoad):
            uniform += load.local_components
        elif isinstance(load, PointMemberLoad):
            point_loads.append(load)
    coefficients[:, 0] += uniform[0] * length**2 / (2*ea) * np.array([0., 1., -1., 0., 0.])
    coefficients[:, 1:] += np.array([0., 0., 1., -2., 1.])[:, None] * (uniform[1:] * length**4 / (24*ei))
    # Uniform temperature/installation strains already enter via nodal motion.
    boundaries = sorted({0.0, length, *(load.position for load in point_loads)})
    original = np.zeros((5, 3))
    original[0] = element.start_node.coordinates
    original[1] = element.end_node.coordinates - element.start_node.coordinates
    segments = []
    for x0, x1 in zip(boundaries, boundaries[1:]):
        interval = coefficients.copy()
        for load in point_loads:
            a = load.position / length
            right = (x0+x1)/2 >= load.position
            axial = np.array([a, -a, 0., 0., 0.]) if right else np.array([0., 1-a, 0., 0., 0.])
            interval[:, 0] += load.local_components[0] * length / ea * axial
            bending = -n3*(1-a)**3 - 3*(n4/length)*(1-a)**2
            if right:
                bending += np.array([-a**3, 3*a*a, -3*a, 1., 0.])
            interval[:, 1:] += bending[:, None] * (load.local_components[1:] * length**3 / (6*ei))
        displacement = _restrict(interval, x0/length, (x1-x0)/length) @ element.rotation
        coordinate = _restrict(original, x0/length, (x1-x0)/length)
        if not np.all(np.isfinite(displacement)):
            raise ValueError(f"杆件 {element_id} 的位移曲线出现非有限数，请检查输入量级。")
        segments.append({"x0": float(x0), "x1": float(x1),
                         "coordinateCoefficients": coordinate.tolist(),
                         "displacementCoefficients": displacement.tolist()})
    return {"version": 1, "length": float(length), "parameter": "t=(x-x0)/(x1-x0)",
            "coefficientOrder": "ascending", "segments": segments, "peak": curve_peak(segments)}


def sample_curve(curve: dict, positions=None, count: int = 81) -> list[dict]:
    """Optional data/export samples; these do NOT control curve rendering."""
    if positions is None:
        if not isinstance(count, int) or count < 2:
            raise ValueError("位移采样点数至少为 2。")
        positions = sorted({*np.linspace(0, curve["length"], count),
                            *(segment["x0"] for segment in curve["segments"])})
    positions = np.asarray(positions, dtype=float)
    if positions.ndim != 1 or not np.all(np.isfinite(positions)) or np.any(positions < 0) or np.any(positions > curve["length"]):
        raise ValueError("位移采样位置必须为 [0, L] 内的有限数。")
    points = []
    for position in positions:
        segment = next(part for part in curve["segments"] if position <= part["x1"])
        parameter = (position-segment["x0"]) / (segment["x1"]-segment["x0"])
        coordinate = polynomial_value(segment["coordinateCoefficients"], parameter)
        displacement = polynomial_value(segment["displacementCoefficients"], parameter)
        points.append({"position": float(position), "coordinate": coordinate.tolist(),
                       "displacement": displacement.tolist(), "magnitude": float(np.linalg.norm(displacement))})
    return points


def recover_element_displacements(model: Model, result: StaticResult, element_id: int,
                                  positions=None, count: int = 81) -> list[dict]:
    return sample_curve(build_element_curve(model, result, element_id), positions, count)

