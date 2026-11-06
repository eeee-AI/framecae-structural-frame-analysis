"""Mesh-independent physical sample locations; exclude singular clamp edge."""
import json
from pathlib import Path
import numpy as np
from .toes import face_owners,project,evaluate_individual,patch_peak
from .tet10 import REFERENCE_NODES,constitutive,mises


def analyze(directory,request):
    directory=Path(directory)
    with np.load(directory/'mesh.npz') as z:p=z['points'];cells=z['tetra10'];tri=z['triangle6']
    with np.load(directory/'solution.npz') as z:u=z['elastic_displacement'];stress=z['element_nodal_stress']
    d=np.asarray(request['geometry']['axis']);r=request['arms'][0]['outerRadius'];coords=p[tri];a=coords@d
    radius=np.linalg.norm(coords-a[:,:,None]*d,axis=2)
    fixed=request['analysisType']=='idealClamp';lo,hi=(.025,.075) if fixed else (-.06,.06)
    selected=np.flatnonzero((np.max(abs(radius-r),axis=1)<2e-6)&(a.min(axis=1)>lo-.02)&(a.max(axis=1)<hi+.02))
    if len(selected)<10:raise ValueError('Missing continuous pipe sample surface')
    v=np.eye(3)[np.argmin(abs(d))];v-=d*(v@d);v/=np.linalg.norm(v);b=np.cross(d,v)
    theta=np.arange(144)*2*np.pi/144;axial=np.linspace(lo,hi,25)
    target=(axial[None,:,None]*d+r*(np.cos(theta)[:,None]*v+np.sin(theta)[:,None]*b)[:,None,:]).reshape(-1,3)
    chosen,uv,gap,_=project(target,coords[selected]);face=selected[chosen];owners,local=face_owners(cells,tri)
    refs=np.einsum('pn,pni->pi',np.c_[1-uv.sum(axis=1),uv],REFERENCE_NODES[local[face,:3]])
    sample=mises(evaluate_individual(p[cells[owners[face]]],u[cells[owners[face]]],constitutive(request['material']['E'],request['material']['nu']),refs))
    # Fixed physical ROI, not triangle-overlap extent, defines the nodal peak.
    axial_nodes=p@d;rad=np.linalg.norm(p-axial_nodes[:,None]*d,axis=1)
    ids=np.flatnonzero((axial_nodes>=lo)&(axial_nodes<=hi)&(abs(rad-r)<2e-6))
    peak,point=patch_peak(p,cells,mises(stress),ids);name='PIPE_ROI'
    records={name:dict(nodePeakMisesPa=peak,peakPoint=point.tolist(),fixedSamplePeakMisesPa=float(sample.max()),maximumProjectionGapM=float(gap.max()),samplingShape=[144,25],definition='all incident element-side stress at nodes inside fixed outer-wall ROI; no averaging',axialRangeM=[lo,hi],sampleDefinition='fixed physical cylindrical surface samples; clamp edge excluded' if fixed else 'fixed physical loading-region surface samples; continuous pipe, no weld')}
    np.savez_compressed(directory/'toe_samples.npz',**{name+'_mises':sample,name+'_points':target,name+'_gap':gap})
    (directory/'toe_results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    (directory/'shoulder_results.json').write_text('{}',encoding='utf-8');return records
