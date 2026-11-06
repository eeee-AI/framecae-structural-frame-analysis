"""Saint-Venant transverse shear of a homogeneous isotropic circular annulus.

This is the closed-form solution of the sectional shear-function problem,
not a uniform shear approximation or a shear-correction-factor adjustment.
For shear along y, psi = a*y + b*y/r**2 - y*r**2/4, with
a=(3+2*nu)*(Ro**2+Ri**2)/4, b=(3+2*nu)*Ro**2*Ri**2/4.
It satisfies Laplacian(psi)=-2*y and zero lateral axial traction at both radii.
The standard isotropic elasticity shear-function relations give the stresses.
Reference: sectionproperties Theory, Shear Properties / Shear Stresses
https://sectionproperties.readthedocs.io/en/latest/user_guide/theory.html

Only transverse shear is replaced. Axial force, bending and torsion keep the
existing distribution. Consistent Tri6 integration preserves virtual work.
An explicitly recorded small quadrature/curved-geometry correction restores
all six resultants on the actual discrete cut; it is not a physical fit.
"""
import numpy as np
from skfem.quadrature import get_quadrature_tri
from .boundary import tri_shape, cross_matrix


def annular_shear_stress(xy, shear, outer, inner, nu):
    """Return [tau_xy,tau_xz] in Pa for a beam along local x; xy are [y,z]."""
    if not (0 <= inner < outer and -1 < nu < .5):
        raise ValueError('Saint-Venant annulus requires 0 <= Ri < Ro and -1 < nu < 0.5')
    xy = np.asarray(xy, dtype=float)
    shear = np.asarray(shear, dtype=float)
    if xy.shape[-1] != 2 or shear.shape != (2,) or not np.isfinite(xy).all() or not np.isfinite(shear).all():
        raise ValueError('Invalid annular sectional coordinates or shear')
    y, z = np.moveaxis(xy / outer, -1, 0)
    radius2 = y*y + z*z
    if inner and np.any(radius2 == 0):
        raise ValueError('Point lies at the centre of a hollow section')
    ratio2 = (inner / outer)**2
    inv_radius4 = np.divide(1., radius2**2, out=np.zeros_like(radius2), where=radius2 != 0)
    c, d = (3+2*nu)/4, (1-2*nu)/4
    h = c*ratio2*inv_radius4
    yy = c*(1+ratio2) - h*(y*y-z*z) - c*y*y - d*z*z
    zz = c*(1+ratio2) - h*(z*z-y*y) - c*z*z - d*y*y
    yz = -(2*h + .5+nu)*y*z
    inertia = np.pi*(outer**4-inner**4)/4
    scale = outer**2/(2*(1+nu)*inertia)
    return scale*np.stack((yy*shear[0]+yz*shear[1], yz*shear[0]+zz*shear[1]), axis=-1)


def replace_shear(points, triangles, arm, nu, ids, C, old):
    """Replace old shear loads, not add another shear load to the same cut."""
    direction = np.asarray(arm['direction']); centre = np.asarray(arm['center'])
    wrench = np.asarray(arm['beamCutWrench']); radius = arm['outerRadius']
    force = wrench[:3] - (wrench[:3]@direction)*direction
    audit = dict(method='saintVenantAnnulus', revision=1, solution='closed_form_isotropic_annulus',
                 axialBendingTorsionUnchanged=True, shearForceGlobal=force.tolist(),
                 maximumCorrectionRelative=0., virtualWorkRelativeError=0.)
    if np.linalg.norm(force) <= 1e-12*max(np.linalg.norm(wrench[:3]),1.):
        audit['negligibleShearBelowProjectionRoundoff']=True
        audit.update(rawShearWrench=[0.]*6, correctedShearWrench=[0.]*6)
        return old.copy(), audit
    # An orthonormal transverse frame; the annulus law is rotation invariant.
    e1 = np.eye(3)[np.argmin(abs(direction))]
    e1 -= (e1@direction)*direction; e1 /= np.linalg.norm(e1)
    e2 = np.cross(direction, e1)
    lookup = np.full(len(points), -1, dtype=int); lookup[ids] = np.arange(len(ids))
    local = lookup[triangles]
    xi, weights = get_quadrature_tri(5); N, grad = tri_shape(xi.T)
    coords = points[triangles]
    locations = np.einsum('qn,fni->fqi', N, coords)
    jac = np.einsum('fni,qnj->fqij', coords, grad)
    area = np.linalg.norm(np.cross(jac[:,:,:,0], jac[:,:,:,1]), axis=-1)*weights
    relative = locations-centre
    xy = np.stack((relative@e1, relative@e2), axis=-1)
    tau = annular_shear_stress(xy, [force@e1, force@e2], radius, arm['innerRadius'], nu)
    traction = tau[...,0,None]*e1 + tau[...,1,None]*e2
    def integrate(t):
        nodal = np.zeros((len(ids), 3))
        per_face = np.einsum('qn,fq,fqi->fni', N, area, t)
        np.add.at(nodal, local.ravel(), per_face.reshape(-1,3))
        return nodal
    def resultant(f):
        return np.r_[f.sum(axis=0), np.cross(points[ids]-centre, f).sum(axis=0)]
    raw = integrate(traction); raw_wrench = resultant(raw)
    target = np.r_[force, np.zeros(3)]; defect = target-raw_wrench
    R = np.concatenate((np.broadcast_to(np.eye(3), (*locations.shape[:2],3,3)),
                        -cross_matrix(relative)/radius), axis=-1)
    gram = np.einsum('fq,fqia,fqib->ab', area, R, R, optimize=True)
    correction = np.einsum('fqia,a->fqi', R, np.linalg.solve(gram, np.r_[defect[:3],defect[3:]/radius]))
    correction_ratio = float(np.sqrt(np.sum(area[...,None]*correction**2)/max(np.sum(area[...,None]*traction**2), 1e-300)))
    if correction_ratio > .01:
        raise ValueError('Saint-Venant cut quadrature correction exceeds 1%; refine the cut surface instead of hiding the discrepancy')
    corrected = traction+correction
    new_shear = integrate(corrected)
    np.testing.assert_allclose(resultant(new_shear), target, rtol=1e-9, atol=1e-7)
    # An arbitrary, non-rigid virtual displacement field on the cut nodes.
    virtual = np.sin(np.arange(3*len(ids))*.731).reshape(-1,3)
    virtual_q = np.einsum('qn,fni->fqi', N, virtual[local])
    nodal_work = float(np.sum(virtual*new_shear))
    surface_work = float(np.sum(area[...,None]*virtual_q*corrected))
    work_error = abs(nodal_work-surface_work)/max(abs(nodal_work),abs(surface_work),np.linalg.norm(force)*1e-12)
    if work_error > 1e-10:
        raise ValueError('Saint-Venant consistent surface-load virtual-work check failed')
    old_shear = (C.T@np.r_[force,np.zeros(3)]).reshape(-1,3)
    total = old-old_shear+new_shear
    np.testing.assert_allclose(resultant(total), wrench, rtol=1e-9, atol=1e-7)
    audit.update(rawShearWrench=raw_wrench.tolist(), correctedShearWrench=resultant(new_shear).tolist(),
                 maximumCorrectionRelative=correction_ratio, virtualWorkRelativeError=work_error,
                 virtualWorkDefinition='nodal work equals corrected-traction surface integral for the same Tri6 interpolated virtual displacement; not a claim of the old mean-motion work pairing')
    return total, audit
