"""Sphere-cylinder shoulder surfaces, sampled independently of mesh labels."""
import json
from pathlib import Path
import numpy as np
from .toes import face_owners,project,evaluate_individual,patch_peak
from .tet10 import constitutive,mises,REFERENCE_NODES

def analyze(directory,request):
    directory=Path(directory)
    with np.load(directory/'mesh.npz') as z:p=z['points'];cells=z['tetra10'];tri=z['triangle6']
    with np.load(directory/'solution.npz') as z:u=z['elastic_displacement'];stress=z['element_nodal_stress']
    owner,local=face_owners(cells,tri);coords=p[tri];D=constitutive(request['material']['E'],request['material']['nu'])
    records={};samples={};H=request['geometry']['hubRadius'];f=request['geometry']['blendWidth'];element_vm=mises(stress)
    for arm in request['arms']:
        d=np.asarray(arm['direction']);R=arm['outerRadius'];rc=R+f;sc=np.sqrt((H+f)**2-rc**2)
        rs=H/(H+f)*rc;ss=H/(H+f)*sc
        axial=coords@d;radial=np.linalg.norm(coords-axial[:,:,None]*d,axis=2)
        error=np.abs(np.sqrt((radial-rc)**2+(axial-sc)**2)-f)
        # Classify the tangent circular blend by geometric coordinates.
        # Keep CAD tolerance for legacy meshes; current arcs are analytic.
        tol=2e-5
        selected=np.flatnonzero((np.max(error,axis=1)<tol)&(np.min(axial,axis=1)>ss-tol)&(np.max(axial,axis=1)<sc+tol))
        if len(selected)<10:raise ValueError('Missing true CAD shoulder fillet')
        peak,peak_point=patch_peak(p,cells,element_vm,np.unique(tri[selected]))
        alpha=np.linspace(np.pi,np.arctan2(ss-sc,rs-rc)+2*np.pi,17)
        radial_profile=rc+f*np.cos(alpha);axial_profile=sc+f*np.sin(alpha)
        a=np.eye(3)[np.argmin(abs(d))];a-=d*(a@d);a/=np.linalg.norm(a);b=np.cross(d,a)
        theta=np.arange(144)*2*np.pi/144;v=np.cos(theta)[:,None]*a+np.sin(theta)[:,None]*b
        targets=(axial_profile[None,:,None]*d+radial_profile[None,:,None]*v[:,None,:]).reshape(-1,3)
        chosen,uv,gap,_=project(targets,coords[selected]);face=selected[chosen]
        refs=np.einsum('pn,pni->pi',np.c_[1-uv.sum(axis=1),uv],REFERENCE_NODES[local[face,:3]])
        values=mises(evaluate_individual(p[cells[owner[face]]],u[cells[owner[face]]],D,refs))
        key='E'+str(arm['element']);records[key]={'peakPa':peak,'point':peak_point.tolist(),
            'surfaceTriangles':len(selected),'maximumProjectionGapM':float(gap.max()),
                'region':f'CAD shoulder blend, {f*1000:g}mm nominal radius; analytic reference points projected onto FE surface; no cross-element averaging'}
        samples[key+'_mises']=values;samples[key+'_triangles']=selected;samples[key+'_points']=targets
    np.savez_compressed(directory/'shoulder_samples.npz',**samples)
    (directory/'shoulder_results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records

def compare(a,b,records):
    out={}
    with np.load(Path(a)/'shoulder_samples.npz') as x,np.load(Path(b)/'shoulder_samples.npz') as y:
        for key,record in records.items():
            delta=x[key+'_mises']-y[key+'_mises'];scale=record['peakPa']
            out[key]={'profileRmsRelativeChange':float(np.sqrt(np.mean(delta*delta))/scale),
                'profileMaxRelativeChange':float(np.max(abs(delta))/scale)}
    return out
