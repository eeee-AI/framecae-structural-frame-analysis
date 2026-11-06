"""Explicit coordinate, action-side and moment-origin conventions for cut audits."""
from __future__ import annotations
import numpy as np


def transport(wrench, source, target):
    """Same external action expressed about another point, in the same XYZ basis."""
    value=np.asarray(wrench,dtype=float).copy()
    value[3:]+=np.cross(np.asarray(source)-np.asarray(target),value[:3])
    return value


def resultant(points, forces, origin):
    points=np.asarray(points,dtype=float);forces=np.asarray(forces,dtype=float)
    return np.r_[forces.sum(axis=0),np.cross(points-np.asarray(origin),forces).sum(axis=0)]


def local_to_global(wrench, rotation):
    """R has local basis vectors in its rows: v_global=R.T@v_local."""
    rotation=np.asarray(rotation,dtype=float);value=np.asarray(wrench,dtype=float)
    return np.r_[rotation.T@value[:3],rotation.T@value[3:]]


def cut_from_node_action(node_action, cut_center):
    """Unloaded retained beam segment: node-on-beam action to exterior-on-segment cut action.

    Node is the origin. q_node + cut_about_node = 0. This independent free-body
    construction uses nodal actions, not the along-member evaluate_section routine.
    """
    return transport(-np.asarray(node_action),np.zeros(3),cut_center)


def compare_wrenches(expected, actual, force_scale, moment_scale, threshold=.05):
    force_scale=float(force_scale);moment_scale=float(moment_scale)
    expected=np.asarray(expected);actual=np.asarray(actual);delta=actual-expected
    fn=float(np.linalg.norm(expected[:3]));mn=float(np.linalg.norm(expected[3:]))
    df=float(np.linalg.norm(delta[:3]));dm=float(np.linalg.norm(delta[3:]))
    # Separate force/moment units; do not construct a norm of all six components.
    # Near-zero reference: report absolute difference and a problem-scale ratio.
    near_f=fn<1e-6*force_scale;near_m=mn<1e-6*moment_scale
    rf=df/(force_scale if near_f else fn);rm=dm/(moment_scale if near_m else mn)
    return {'difference':delta.tolist(),'forceDifferenceN':df,'momentDifferenceNm':dm,
            'forceReferenceNearZero':near_f,'momentReferenceNearZero':near_m,
            'forceRelativeToBeam':None if near_f else df/fn,
            'momentRelativeToBeam':None if near_m else dm/mn,
            'forceRelativeToProblemScale':df/force_scale,
            'momentRelativeToProblemScale':dm/moment_scale,
            'forceCheckValue':rf,'momentCheckValue':rm,
            'forcePassed':rf<=threshold,'momentPassed':rm<=threshold,
            'passed':rf<=threshold and rm<=threshold}
