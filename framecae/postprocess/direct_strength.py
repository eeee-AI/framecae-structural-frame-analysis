"""Continuous circumference extrema and bounded piecewise axial maximization.
The stress recovery law is unchanged. No fixed angular or axial strength grid.
"""
import numpy as np
from numpy.polynomial import Polynomial as P
from .internal_force import element_force_segments


def _real_roots(poly):
    c=np.asarray(poly.coef,float)
    scale=np.max(np.abs(c))
    if scale<1e-25:return []
    poly=P(c/scale).trim(1e-12)
    if poly.degree()<1:return []
    return [float(z.real) for z in poly.roots() if abs(z.imag)<1e-5*(1+abs(z.real))]


def critical_angles(element,forces,options):
    """All stationary/cusp candidates via tan(theta/2) polynomial equations.
    Squaring the spectral criteria can introduce extra roots; evaluating these is
    safe. The angle pi, absent from finite tan-half-angle coordinates, is explicit.
    """
    sec=element.section;R=sec.characteristic_size/2
    n,vy,vz,t,my,mz=np.asarray(forces,float)
    a=n/sec.area;b=R*mz/sec.iz;c=R*my/sec.iy
    u=vy/sec.area if options.include_average_transverse_shear else 0.
    v=vz/sec.area if options.include_average_transverse_shear else 0.
    torsion=t*R/sec.torsion_constant
    scale=max(abs(a),abs(b),abs(c),abs(u),abs(v),abs(torsion),1e-100)
    a,b,c,u,v,torsion=np.array([a,b,c,u,v,torsion])/scale
    # Without mean transverse shear, torsion magnitude is constant around the rim.
    if abs(u)+abs(v)<1e-14 or abs(torsion)<1e-14:
        if abs(b)+abs(c)<1e-14:return [0.]
        theta=float(np.arctan2(c,b)%(2*np.pi))
        return [theta,(theta+np.pi)%(2*np.pi)]
    D=P([1,0,1]);C=P([1,0,-1]);S=P([0,2])
    A=a*D+b*C+c*S
    H=(u*u+v*v+torsion*torsion)*D+2*torsion*v*C-2*torsion*u*S
    derivative=A.deriv()*D-A*D.deriv()
    polys=[A,derivative]
    for factor in (3.,4.):
        Q=A*A+factor*H*D
        B=Q.deriv()*D-2*Q*D.deriv()
        polys.extend([Q,B])
        if factor==4:
            # Rankine and max strain have the form alpha*sigma +/- beta*sqrt(Q).
            nu=element.material.poisson_ratio
            for alpha,beta in ((1.,1.),(1.-nu,1.+nu)):
                polys.append(4*alpha**2*derivative**2*Q-beta**2*B**2)
    angles=[0.,np.pi]
    for poly in polys:angles.extend((2*np.arctan(x))%(2*np.pi) for x in _real_roots(poly))
    return sorted(set(round(float(x),13) for x in angles))


def section_extrema(element,position,forces,options):
    from .strength_check import evaluate_strength_point,THEORY_LABELS
    angles=critical_angles(element,forces,options)
    points=[evaluate_strength_point(element,position,forces,x,options) for x in angles]
    return {k:max(points,key=lambda p:p.utilizations[k]) for k in THEORY_LABELS},len(points)


def member_extrema(model,result,element,options):
    """Endpoint solution for affine stress; Bernstein enclosure for distributed loads.
    Each strength criterion is a convex function of the recovered stress tensor.
    On an interval the quadratic force field lies in the convex hull of its three
    Bernstein control vectors. Circumferential maxima at the controls therefore
    bound every physical section in that interval, including nonsmooth switches.
    """
    from .strength_check import THEORY_LABELS
    keys=tuple(THEORY_LABELS);best={};count=0;branches=0;max_gap=0.
    def accept(position,forces):
        nonlocal count
        answers,number=section_extrema(element,position,forces,options);count+=number
        for k in keys:
            if k not in best or answers[k].utilizations[k]>best[k].utilizations[k]:best[k]=answers[k]
        return answers
    segments=element_force_segments(model,result,element.id)
    # Include the actual right-hand state at every knot, including loads at x=L.
    from .internal_force import evaluate_section
    accept(element.length,evaluate_section(model,result,element.id,element.length).forces)
    for lower,upper,f0,linear,quadratic in segments:
        force=lambda t:f0+linear*t+quadratic*t*t
        def position(t):
            x=lower+(upper-lower)*t
            # At a jump the left limit belongs to the preceding open segment.
            return float(np.nextafter(upper,lower)) if t==1 else x
        f1=force(1.)
        accept(position(0),f0);accept(position(1),f1)
        if not np.any(quadratic):continue
        pending=[(0.,1.,f0,f1)]
        while pending:
            left,right,fl,fr=pending.pop();mid=(left+right)/2;fm=force(mid)
            middle=accept(position(mid),fm)
            controls,_=section_extrema(element,position(mid),2*fm-.5*(fl+fr),options)
            # Endpoints are actual sections and cannot exceed the global incumbent.
            gaps={k:max(0.,controls[k].utilizations[k]-best[k].utilizations[k]) for k in keys}
            tolerances={k:max(1e-10,options.extremum_tolerance*best[k].utilizations[k]) for k in keys}
            if all(gaps[k]<=tolerances[k] for k in keys):
                max_gap=max(max_gap,max(gaps.values()));continue
            branches+=1
            if branches>8192 or right-left<1e-13:
                raise ValueError('分段强度极值未达到误差容差，未返回未经确认的最大值。请检查工况与截面参数。')
            pending.extend(((left,mid,fl,fm),(mid,right,fm,fr)))
    return best,count,{'subdivisions':branches,'maximumUtilizationEnclosureGap':max_gap}
