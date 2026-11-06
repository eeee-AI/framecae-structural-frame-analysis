"""Independent boundary stress-flux recovery, distinct from imposed nodal loads."""
import json
from pathlib import Path
import numpy as np
from skfem.quadrature import get_quadrature_tri
from .boundary import tri_shape
from .tet10 import constitutive,REFERENCE_NODES
from .toes import face_owners,evaluate_individual


def analyze(directory,request):
    directory=Path(directory)
    with np.load(directory/'mesh.npz') as z:
        p=z['points'];cells=z['tetra10'];tri=z['triangle6'];cuts={str(a['element']):z['cut_E'+str(a['element'])] for a in request['arms']}
    with np.load(directory/'solution.npz') as z:u=z['elastic_displacement']
    owner,local=face_owners(cells,tri);xi,w=get_quadrature_tri(5);uv=xi.T;N,grad=tri_shape(uv);records=[]
    D=constitutive(request['material']['E'],request['material']['nu'])
    for arm in request['arms']:
        mask=np.zeros(len(p),bool);mask[cuts[str(arm['element'])]]=True;ids=np.flatnonzero(np.all(mask[tri],axis=1));f=tri[ids];coords=p[f]
        refs=np.einsum('qn,fni->fqi',np.c_[1-uv.sum(axis=1),uv],REFERENCE_NODES[local[ids,:3]])
        s=evaluate_individual(np.repeat(p[cells[owner[ids]]],len(w),axis=0),np.repeat(u[cells[owner[ids]]],len(w),axis=0),D,refs.reshape(-1,3)).reshape(len(f),len(w),6)
        d=np.asarray(arm['direction']);t=np.stack([s[:,:,0]*d[0]+s[:,:,3]*d[1]+s[:,:,4]*d[2],s[:,:,3]*d[0]+s[:,:,1]*d[1]+s[:,:,5]*d[2],s[:,:,4]*d[0]+s[:,:,5]*d[1]+s[:,:,2]*d[2]],axis=2)
        q=np.einsum('qn,fni->fqi',N,coords);J=np.einsum('fni,qnj->fqij',coords,grad);area=np.linalg.norm(np.cross(J[:,:,:,0],J[:,:,:,1]),axis=2)*w
        force=np.einsum('fq,fqi->i',area,t);moment=np.einsum('fq,fqi->i',area,np.cross(q-arm['center'],t));actual=np.r_[force,moment];expected=np.asarray(arm['beamCutWrench'])
        df=float(np.linalg.norm(actual[:3]-expected[:3])/max(np.linalg.norm(expected[:3]),1.));dm=float(np.linalg.norm(actual[3:]-expected[3:])/max(np.linalg.norm(expected[3:]),1.))
        records.append(dict(element=arm['element'],stressIntegratedWrench=actual.tolist(),beamExpected=expected.tolist(),forceRelativeDifference=df,momentRelativeDifference=dm,passed=max(df,dm)<=.05))
    answer=dict(definition='Integrate recovered FE stress sigma*n on actual annular cut; global XYZ and moment about each cut centre. This does not read the prescribed cut nodal forces.',passed=all(r['passed'] for r in records),cuts=records)
    (directory/'cut_stress_flux.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding='utf-8');return answer
