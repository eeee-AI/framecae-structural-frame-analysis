"""Closest-point CAD placement avoids periodic-parametric midside jumps."""
import numpy as np
import gmsh


def audit_endpoints(curves,tolerance=1e-6):
    worst=0.;count=0
    for entity in curves:
        vertices=gmsh.model.getBoundary([(1,entity)],oriented=False)
        if not vertices:continue
        points=np.array([gmsh.model.getValue(0,tag,[]) for dim,tag in vertices])
        x,_=gmsh.model.getClosestPoint(1,entity,points.ravel());x=np.asarray(x).reshape(-1,3)
        delta=np.linalg.norm(x-points,axis=1);suspect=delta>1e-8
        if suspect.any():
            local,_=local_closest(1,entity,points[suspect]);delta[suspect]=np.minimum(delta[suspect],np.linalg.norm(local-points[suspect],axis=1))
        count+=len(points);worst=max(worst,float(delta.max()))
    if worst>tolerance:raise ValueError(f'CAD curve/vertex mismatch {worst:g} m exceeds {tolerance:g} m; refuse to mesh')
    return dict(passed=True,checkedCurveEndpoints=count,maximumEndpointGapM=worst,toleranceM=tolerance)


def local_closest(dim,entity,targets):
    """Seed in parameter space, then minimize physical distance locally.

    OCC's generic projection can return an antipodal stationary point on a
    periodic surface. A spatial seed and descent select the nearby solution.
    Every returned point is evaluated on the actual CAD entity.
    """
    from scipy.spatial import cKDTree
    low,high=gmsh.model.getParametrizationBounds(dim,entity);low=np.asarray(low);high=np.asarray(high);span=high-low
    axes=[np.linspace(a,b,49) for a,b in zip(low,high)];grid=np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1).reshape(-1,dim)
    cloud=np.asarray(gmsh.model.getValue(dim,entity,grid.ravel())).reshape(-1,3);uv=grid[cKDTree(cloud).query(targets)[1]].copy()
    for _ in range(24):
        x=np.asarray(gmsh.model.getValue(dim,entity,uv.ravel())).reshape(-1,3)
        jac=np.asarray(gmsh.model.getDerivative(dim,entity,uv.ravel())).reshape(-1,dim,3).transpose(0,2,1)
        gram=np.einsum('pia,pib->pab',jac,jac);rhs=np.einsum('pia,pi->pa',jac,x-targets)
        gram+=np.eye(dim)[None]*np.maximum(np.trace(gram,axis1=1,axis2=2),1e-30)[:,None,None]*1e-13
        step=np.linalg.solve(gram,rhs[...,None])[...,0];step=np.clip(step,-.2*span,.2*span)
        base=np.sum((x-targets)**2,axis=1);factor=np.ones(len(uv));chosen=uv.copy();pending=np.ones(len(uv),bool)
        for j in range(12):
            trial=np.clip(uv-step*factor[:,None],low,high);val=np.asarray(gmsh.model.getValue(dim,entity,trial.ravel())).reshape(-1,3)
            better=pending&(np.sum((val-targets)**2,axis=1)<=base+1e-28);chosen[better]=trial[better];pending[better]=False;factor[pending]*=.5
            if not pending.any():break
        if np.max(abs(chosen-uv))<1e-12:uv=chosen;break
        uv=chosen
    return np.asarray(gmsh.model.getValue(dim,entity,uv.ravel())).reshape(-1,3),uv


def place_midsides():
    tags,coords,_=gmsh.model.mesh.getNodes();tags=np.asarray(tags);order=np.argsort(tags);tags=tags[order];coords=np.asarray(coords).reshape(-1,3)[order]
    types,_,raw=gmsh.model.mesh.getElements(3)
    if any(t!=11 for t in types):raise ValueError('Expected quadratic tetrahedra')
    # Gmsh's native Tet10 edge order is obtained from reference coordinates.
    prop=gmsh.model.mesh.getElementProperties(11);ref=np.asarray(prop[4]).reshape(-1,3);corners=ref[:4]
    pairs=[]
    for x in ref[4:]:
        pair=min(((i,j) for i in range(4) for j in range(i+1,4)),key=lambda ab:np.linalg.norm((corners[ab[0]]+corners[ab[1]])/2-x));pairs.append(pair)
    conn=np.vstack([np.asarray(v).reshape(-1,10) for v in raw]);mid=conn[:,4:].ravel();ends=np.stack([conn[:,[a,b]] for a,b in pairs],axis=1).reshape(-1,2)
    unique,first=np.unique(mid,return_index=True);ends=ends[first];target=coords[np.searchsorted(tags,ends)].mean(axis=1)
    chord=np.linalg.norm(coords[np.searchsorted(tags,ends[:,0])]-coords[np.searchsorted(tags,ends[:,1])],axis=1)
    ids=np.searchsorted(tags,unique);old=coords[ids].copy();new=target.copy();boundary=np.zeros(len(unique),bool)
    for dim in (1,2):
        for _,entity in gmsh.model.getEntities(dim):
            owned=gmsh.model.mesh.getNodes(dim,entity,includeBoundary=False)[0]
            common,index,_=np.intersect1d(unique,owned,return_indices=True)
            if not len(common):continue
            xyz,param=gmsh.model.getClosestPoint(dim,entity,target[index].ravel())
            xyz=np.asarray(xyz).reshape(-1,3);param=np.asarray(param).reshape(-1,dim)
            if not np.isfinite(xyz).all():raise ValueError('Nonfinite CAD midside projection')
            suspicious=np.linalg.norm(xyz-target[index],axis=1)>np.maximum(.12*chord[index],1e-8)
            if suspicious.any():
                local,uv=local_closest(dim,entity,target[index[suspicious]])
                take=np.linalg.norm(local-target[index[suspicious]],axis=1)<np.linalg.norm(xyz[suspicious]-target[index[suspicious]],axis=1)
                positions=np.flatnonzero(suspicious)[take];xyz[positions]=local[take];param[positions]=uv[take]
            new[index]=xyz;boundary[index]=True
            for nid,p,uv in zip(common,xyz,param):gmsh.model.mesh.setNode(int(nid),p,uv)
    # Interior edge nodes retain the exact straight-edge midpoint initially.
    for nid,p in zip(unique[~boundary],new[~boundary]):gmsh.model.mesh.setNode(int(nid),p,[])
    displacement=np.linalg.norm(new-old,axis=1)
    return dict(boundaryMidsides=int(boundary.sum()),maximumCorrectionM=float(displacement.max()),largePeriodicJumpsRepaired=int(np.count_nonzero(displacement>.5*chord)))
