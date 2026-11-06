"""Consistent retained-line loading; no change to cut Saint-Venant tractions.

Each integration point belongs to one arm, including the shared hub. A minimum
L2 density reproduces the work of q on all 12 beam virtual DOFs, evaluated with
the SAME Tet10 interpolation as the solid. It therefore reproduces rigid-body
force/moment work too. This is an equivalent volume load, not surface pressure.
"""
import numpy as np
from .tet10 import shape, gradients, get_quadrature_tet


def beam_virtual_field(x, rotation, length):
    """3 x 12 local displacement matrix; rotational columns scaled by 1/L."""
    x = np.asarray(x) @ rotation.T
    s = np.clip(x[..., 0], 0., length); t = s/length
    h1 = 1-3*t*t+2*t**3; h2 = t-2*t*t+t**3
    h3 = 3*t*t-2*t**3; h4 = -t*t+t**3
    dh1 = (-6*t+6*t*t)/length; dh2 = 1-4*t+3*t*t
    dh3 = (6*t-6*t*t)/length; dh4 = -2*t+3*t*t
    H = np.zeros(x.shape[:-1]+(3,12)); W = np.zeros_like(H)
    H[...,0,0]=1-t; H[...,0,6]=t
    H[...,1,1]=h1; H[...,1,5]=length*h2; H[...,1,7]=h3; H[...,1,11]=length*h4
    H[...,2,2]=h1; H[...,2,4]=-length*h2; H[...,2,8]=h3; H[...,2,10]=-length*h4
    W[...,0,3]=1-t; W[...,0,9]=t
    W[...,1,2]=-dh1; W[...,1,4]=dh2; W[...,1,8]=-dh3; W[...,1,10]=dh4
    W[...,2,1]=dh1; W[...,2,5]=dh2; W[...,2,7]=dh3; W[...,2,11]=dh4
    off=x.copy(); off[...,0]-=s
    H += np.moveaxis(np.cross(np.moveaxis(W,-1,-2),off[...,None,:]),-2,-1)
    H[..., [3,4,5,9,10,11]] /= length
    return H


def equivalent_loads(points, cells, request, chunk=256):
    mapping=request.get('memberLoadMapping')
    loads=np.zeros_like(points,dtype=float)
    if not mapping:return loads,None
    arms=request['arms']; specs={a['element']:a for a in mapping['loads']}
    xi,w=get_quadrature_tet(5); N,_=shape(xi.T)
    directions=np.asarray([a['direction'] for a in arms]); lengths=np.asarray([a['length'] for a in arms])
    radii=np.asarray([a['outerRadius'] for a in arms])
    records=[]
    # A deterministic arbitrary FE virtual field checks consistent integration.
    probe=np.sin(points*np.array([1.3,2.1,3.7])+.37)
    for arm_index,arm in enumerate(arms):
        spec=specs.get(arm['element'])
        if spec is None:continue
        L=arm['length']; ex=np.asarray(arm['direction']);ey=np.asarray(arm['beamRotation'])[1]
        R=np.asarray([ex,ey,np.cross(ex,ey)])
        if not np.allclose(R@R.T,np.eye(3),atol=1e-10):raise ValueError('Invalid outward arm axes')
        q=R@np.asarray(spec['globalQ']); gram=np.zeros((12,12));vol=0.
        def chunks():
            for start in range(0,len(cells),chunk):
                conn=cells[start:start+chunk]; xyz=points[conn]
                _,det=gradients(xyz,xi.T)
                if np.any(det<=0):raise ValueError('Line-load integration encountered nonpositive Jacobian')
                qp=np.einsum('qn,eni->eqi',N,xyz)
                s=np.clip(qp@directions.T,0.,lengths)
                delta=qp[:,:,None,:]-s[...,None]*directions
                owner=np.argmin(np.sum(delta*delta,axis=-1)/radii**2,axis=-1)
                weight=det*w*(owner==arm_index)
                if not np.any(weight):continue
                Hn=beam_virtual_field(xyz,R,L)
                H=np.einsum('qn,enic->eqic',N,Hn,optimize=True)
                yield conn,weight,Hn,H
        for conn,weight,Hn,H in chunks():
            gram+=np.einsum('eqic,eqid,eq->cd',H,H,weight,optimize=True);vol+=weight.sum()
        # Exact constant q work against the original cubic beam field on its axis.
        a,b=np.polynomial.legendre.leggauss(5);s=(a+1)*L/2
        target=np.einsum('qic,i,q->c',beam_virtual_field(s[:,None]*ex,R,L),q,b*L/2)
        condition=float(np.linalg.cond(gram))
        if not vol>0 or not np.isfinite(condition) or condition>1e13:
            raise ValueError(f'E{arm["element"]}等效加载区域无法表示梁虚功，Gram条件数={condition:g}；请调整几何或网格。')
        multipliers=np.linalg.solve(gram,target)
        part=np.zeros_like(points); quadrature_work=0.
        for conn,weight,Hn,H in chunks():
            density=np.einsum('eqic,c->eqi',H,multipliers)@R
            forces=np.einsum('qn,eqi,eq->eni',N,density,weight,optimize=True)
            for j in range(10):np.add.at(part,conn[:,j],forces[:,j])
            vp=np.einsum('qn,eni->eqi',N,probe[conn])
            quadrature_work+=np.einsum('eqi,eqi,eq->',vp,density,weight)
        actual=np.einsum('nic,ni->c',beam_virtual_field(points,R,L),part@R.T,optimize=True)
        expected=np.r_[np.asarray(spec['globalQ'])*L,np.cross(ex,np.asarray(spec['globalQ']))*L**2/2]
        wrench=np.r_[part.sum(axis=0),np.cross(points,part).sum(axis=0)]
        fe_work=float(np.sum(part*probe))
        work_error=float(np.linalg.norm(actual-target)/max(np.linalg.norm(target),1.))
        integral_error=float(abs(fe_work-quadrature_work)/max(abs(fe_work),abs(quadrature_work),1.))
        force_error=float(np.linalg.norm(wrench[:3]-expected[:3])/max(np.linalg.norm(expected[:3]),1.))
        moment_error=float(np.linalg.norm(wrench[3:]-expected[3:])/max(np.linalg.norm(expected[3:]),1.))
        passed=max(work_error,integral_error,force_error,moment_error)<1e-9
        if not passed:raise ValueError(f'E{arm["element"]}均布荷载守恒/虚功检查失败')
        records.append({**spec,'assignedVolumeM3':float(vol),'gramCondition':condition,
            'expectedWrenchAtNode':expected.tolist(),'actualWrenchAtNode':wrench.tolist(),
            'beamVirtualWorkRelativeError':work_error,'discreteVirtualWorkRelativeError':integral_error,
            'forceRelativeError':force_error,'momentRelativeError':moment_error,'passed':passed})
        loads+=part
    audit={**mapping,'arms':records,'passed':all(r['passed'] for r in records),
        'resultantAtNode':np.r_[loads.sum(axis=0),np.cross(points,loads).sum(axis=0)].tolist(),
        'assumption':'整杆恒定q在局部0..cut上的最小L2等效体积加载；12个离散梁虚功约束。非实际表面压力。'}
    return loads,audit
