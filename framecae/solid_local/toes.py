"""Fixed geometric toe surfaces, curved-face projection and one-sided stress."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from .boundary import tri_shape
from .tet10 import shape,constitutive,mises,REFERENCE_NODES


def paths(request,angles=144,meridian=17):
    g=request['geometry'];out={}
    for arm in request['arms']:
        d=np.asarray(arm['direction']);r=arm['outerRadius'];t=g['toeRadius'];h=g['reinforcement'];width=g['weldWidth'];station=g['weldDistance']
        crown=(width*width/4+h*h)/(2*h)-t;c1=np.array([r+t,station-width/2]);c2=np.array([r+h-crown,station])
        touch=c1+t/(t+crown)*(c2-c1);alpha=np.linspace(np.pi,np.arctan2(*(touch-c1)[::-1]),meridian)
        profile=c1[:,None]+t*np.array([np.cos(alpha),np.sin(alpha)])
        u=np.eye(3)[np.argmin(np.abs(d))];u-=d*(u@d);u/=np.linalg.norm(u);v=np.cross(d,u)
        theta=np.arange(angles)*2*np.pi/angles;radial=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
        for side in ['near','far']:
            axial=profile[1] if side=='near' else 2*station-profile[1]
            p=axial[None,:,None]*d+profile[0][None,:,None]*radial[:,None,:]
            out[f'E{arm["element"]}_{side}']={'points':p.reshape(-1,3),'element':arm['element'],'direction':d,
                'toeCenterAxial':station+(-1 if side=='near' else 1)*width/2,
                'side':side,'outerRadius':r,'toeRadius':t,'shape':[angles,meridian]}
    return out


def face_owners(cells,triangles):
    patterns=np.array([[0,2,1],[0,1,3],[1,2,3],[2,0,3]])
    vertices=np.sort(cells[:,patterns].reshape(-1,3),axis=1)
    dtype=np.dtype([('a',np.int32),('b',np.int32),('c',np.int32)])
    keys=np.ascontiguousarray(vertices,dtype=np.int32).view(dtype).ravel();order=np.argsort(keys);sorted_keys=keys[order]
    boundary=np.ascontiguousarray(np.sort(triangles[:,:3],axis=1),dtype=np.int32).view(dtype).ravel()
    index=np.searchsorted(sorted_keys,boundary)
    if not np.array_equal(sorted_keys[index],boundary):raise ValueError('Boundary facet not found in Tet10 mesh')
    owners=(order[index]//4).astype(np.int32)
    local=np.argmax(triangles[:,:,None]==cells[owners,None,:],axis=2)
    if not np.array_equal(np.take_along_axis(cells[owners],local,axis=1),triangles):raise ValueError('Boundary midside connectivity mismatch')
    return owners,local


def project(points,coordinates,candidates=16):
    tree=cKDTree(coordinates[:,:3].mean(axis=1));_,ids=tree.query(points,k=min(candidates,len(coordinates)))
    if ids.ndim==1:ids=ids[:,None]
    count=ids.shape[1];coords=coordinates[ids.ravel()];target=np.repeat(points,count,axis=0)
    edge=np.stack((coords[:,1]-coords[:,0],coords[:,2]-coords[:,0]),axis=2)
    uv=np.linalg.solve(np.einsum('mij,mik->mjk',edge,edge),np.einsum('mij,mi->mj',edge,target-coords[:,0])[...,None])[...,0]
    for _ in range(9):
        uv=np.maximum(uv,0);uv/=np.maximum(uv.sum(axis=1,keepdims=True),1.)
        n,g=tri_shape(uv);x=np.einsum('mn,mni->mi',n,coords);J=np.einsum('mni,mnj->mij',coords,g)
        step=np.linalg.solve(np.einsum('mij,mik->mjk',J,J),np.einsum('mij,mi->mj',J,x-target)[...,None])[...,0]
        uv-=step
    uv=np.maximum(uv,0);uv/=np.maximum(uv.sum(axis=1,keepdims=True),1.)
    n,_=tri_shape(uv);x=np.einsum('mn,mni->mi',n,coords)
    distance=np.linalg.norm(x-target,axis=1).reshape(len(points),count)
    best=np.argmin(distance,axis=1);flat=np.arange(len(points))*count+best
    return ids[np.arange(len(points)),best],uv[flat],distance[np.arange(len(points)),best],x[flat]


def evaluate_individual(coordinates,displacement,D,xi):
    _,gref=shape(xi);J=np.einsum('pni,pnj->pij',coordinates,gref)
    if np.any(np.linalg.det(J)<=0):raise ValueError('Invalid Jacobian at toe sample')
    grad=np.einsum('pnj,pji->pni',gref,np.linalg.inv(J));H=np.einsum('pni,pnj->pij',displacement,grad)
    eps=np.stack((H[:,0,0],H[:,1,1],H[:,2,2],H[:,0,1]+H[:,1,0],H[:,0,2]+H[:,2,0],H[:,1,2]+H[:,2,1]),axis=1)
    return eps@D.T


def patch_peak(points,cells,element_vm,patch_nodes):
    mask=np.zeros(len(points),dtype=bool);mask[np.asarray(patch_nodes,dtype=int)]=True
    values=np.where(mask[cells],element_vm,-np.inf)
    i,j=np.unravel_index(np.argmax(values),values.shape)
    if not np.isfinite(values[i,j]):raise ValueError('Empty or invalid patch stress')
    return float(values[i,j]),points[cells[i,j]]


def analyze(directory,request):
    directory=Path(directory)
    with np.load(directory/'mesh.npz') as z:p=z['points'];cells=z['tetra10'];tri=z['triangle6']
    with np.load(directory/'solution.npz') as z:u=z['elastic_displacement'];stress=z['element_nodal_stress']
    owners,local=face_owners(cells,tri);D=constitutive(request['material']['E'],request['material']['nu']);records={};saved={}
    element_vm=mises(stress)
    all_paths=paths(request);coords=p[tri]
    for name,path in all_paths.items():
        d=path['direction'];r=path['outerRadius'];t=path['toeRadius'];station=path['toeCenterAxial']
        axial=coords@d;radial=np.linalg.norm(coords-axial[:,:,None]*d,axis=2)
        err=np.abs(np.sqrt((radial-r-t)**2+(axial-station)**2)-t)
        region=(np.max(err,axis=1)<1e-7)&(np.max(np.abs(axial-station),axis=1)<t*.8)
        if path['side']=='near':region&=np.min(axial-station,axis=1)>-1e-7
        else:region&=np.max(axial-station,axis=1)<1e-7
        selected=np.flatnonzero(region)
        if len(selected)<10:raise ValueError('Missing toe surface: '+name)
        # At a shared patch edge, retain every incident element's trace, not
        # just the element owning the fillet-side surface triangle.
        peak,peak_point=patch_peak(p,cells,element_vm,np.unique(tri[selected]))
        chosen,uv,gap,projected=project(path['points'],coords[selected])
        face=selected[chosen];owner=owners[face]
        corner_refs=REFERENCE_NODES[local[face,:3]];l=np.c_[1-uv.sum(axis=1),uv]
        refs=np.einsum('pn,pni->pi',l,corner_refs)
        field=evaluate_individual(p[cells[owner]],u[cells[owner]],D,refs);sample=mises(field)
        records[name]={'nodePeakMisesPa':peak,'peakPoint':peak_point.tolist(),'fixedSamplePeakMisesPa':float(sample.max()),
            'boundaryTriangles':len(selected),'maximumProjectionGapM':float(gap.max()),'projectionRmsGapM':float(np.sqrt(np.mean(gap*gap))),
            'definition':'maximum over all incident element-side stresses at curved toe patch nodes, including both sides of junction curves; no cross-element smoothing',
            'samplingShape':path['shape'],'sampleDefinition':'FE stress evaluated on nearest curved Tri6 projection of fixed CAD toe points'}
        saved[name+'_mises']=sample;saved[name+'_points']=path['points'];saved[name+'_gap']=gap
        saved[name+'_triangles']=selected
        print('TOE',name,peak/1e6,'MPa','gap',gap.max(),flush=True)
    np.savez_compressed(directory/'toe_samples.npz',**saved)
    (directory/'toe_results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records


def compare(a,b):
    a=Path(a);b=Path(b);ra=json.loads((a/'toe_results.json').read_text('utf-8'));rb=json.loads((b/'toe_results.json').read_text('utf-8'))
    out={}
    with np.load(a/'toe_samples.npz') as sa,np.load(b/'toe_samples.npz') as sb:
        for key,v in rb.items():
            scale=v['nodePeakMisesPa'];delta=sa[key+'_mises']-sb[key+'_mises']
            out[key]={'peakRelativeChange':abs(ra[key]['nodePeakMisesPa']-scale)/scale,
                'profileRmsRelativeChange':float(np.sqrt(np.mean(delta*delta))/scale),
                'profileMaxRelativeChange':float(np.max(np.abs(delta))/scale)}
    return {'changes':out,'peakPassed':all(v['peakRelativeChange']<=.05 for v in out.values()),
            'profileRmsPassed':all(v['profileRmsRelativeChange']<=.05 for v in out.values()),
            'profileMaxPassed':all(v['profileMaxRelativeChange']<=.05 for v in out.values())}
