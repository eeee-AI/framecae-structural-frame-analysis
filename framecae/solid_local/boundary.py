"""Cut observation/rigid pose and consistent curved-surface force/moment loading."""
import numpy as np
from skfem.quadrature import get_quadrature_tri


def cross_matrix(r):
    r=np.asarray(r);M=np.zeros((*r.shape[:-1],3,3));x,y,z=np.moveaxis(r,-1,0)
    M[...,0,1]=-z;M[...,0,2]=y;M[...,1,0]=z;M[...,1,2]=-x;M[...,2,0]=-y;M[...,2,1]=x
    return M


def cut_observations(points,request,cut_sets=None):
    """Identify cut nodes and fit a rigid pose; impose NO displacement BC."""
    cuts={};target=np.zeros_like(points);seen=np.zeros(len(points),dtype=bool)
    for arm in request['arms']:
        d=np.asarray(arm['direction']);c=np.asarray(arm['center'])
        axial=points@d;radial=np.linalg.norm(points-axial[:,None]*d,axis=1)
        ids=np.asarray(cut_sets[str(arm['element'])],dtype=int) if cut_sets is not None else np.flatnonzero((abs(axial-arm['length'])<1e-7)&(radial>=arm['innerRadius']-1e-7)&(radial<=arm['outerRadius']+1e-7))
        if len(ids)<6:raise ValueError('Cut missing')
        values=np.asarray(arm['translation'])+np.cross(np.asarray(arm['rotation']),points[ids]-c)
        if np.any(seen[ids]):raise ValueError('Overlapping cut surfaces')
        target[ids]=values;seen[ids]=True;cuts[str(arm['element'])]=ids
    nodes=np.flatnonzero(seen);dofs=(nodes[:,None]*3+np.arange(3)).ravel()
    A=np.concatenate((np.broadcast_to(np.eye(3),(len(nodes),3,3)),-cross_matrix(points[nodes])),axis=2).reshape(-1,6)
    gauge=np.linalg.lstsq(A,target[nodes].ravel(),rcond=None)[0]
    rigid=gauge[:3]+np.cross(gauge[3:],points)
    return cuts,dofs,target[nodes].ravel(),rigid,gauge


def tri_shape(xi):
    xi=np.atleast_2d(xi);l=np.c_[1-xi.sum(axis=1),xi];dl=np.array([[-1.,-1],[1,0],[0,1]])
    n=np.empty((len(xi),6));g=np.empty((len(xi),6,2));n[:,:3]=l*(2*l-1);g[:,:3]=(4*l-1)[:,:,None]*dl
    for k,(a,b) in enumerate([(0,1),(1,2),(0,2)],3):n[:,k]=4*l[:,a]*l[:,b];g[:,k]=4*(l[:,b,None]*dl[a]+l[:,a,None]*dl[b])
    return n,g


def load_cap(points,triangles,request):
    if request.get('analysisType') in ('continuousPipe','idealClamp'):
        return pipe_patch(points,triangles,request)
    d=np.asarray(request['load']['direction']);radius=request['load']['radius'];hub=request['geometry']['hubRadius']
    target=np.asarray(request['load']['wrench']);loads=np.zeros((len(points),3))
    if np.linalg.norm(target)==0:return loads,{'resultant':np.zeros(6).tolist(),'triangles':0}
    centers=points[triangles[:,:3]].mean(axis=1);a=centers@d;rad=np.linalg.norm(centers-a[:,None]*d,axis=1)
    selected=(a>np.sqrt(hub*hub-radius*radius)*.97)&(rad<radius)&(np.linalg.norm(centers,axis=1)<hub*1.08)
    faces=triangles[selected]
    if len(faces)<4:raise ValueError('Load cap too coarse')
    xi,w=get_quadrature_tri(5);N,g=tri_shape(xi.T);coords=points[faces]
    q=np.einsum('qn,fni->fqi',N,coords);J=np.einsum('fni,qnj->fqij',coords,g)
    area=np.linalg.norm(np.cross(J[:,:,:,0],J[:,:,:,1]),axis=-1)*w
    M=np.zeros((*q.shape[:2],6,3));M[:,:,:3,:]=np.eye(3);M[:,:,3:,:]=cross_matrix(q)
    gram=np.einsum('fq,fqij,fqkj->ik',area,M,M,optimize=True)
    coefficients=np.linalg.solve(gram,target)
    traction=np.einsum('fqij,i->fqj',M,coefficients)
    nodal=np.einsum('qn,fq,fqi->fni',N,area,traction,optimize=True)
    np.add.at(loads,faces.ravel(),nodal.reshape(-1,3))
    recovered=np.r_[loads.sum(axis=0),np.cross(points,loads).sum(axis=0)]
    np.testing.assert_allclose(recovered,target,atol=1e-6,rtol=1e-9)
    return loads,{'resultant':recovered.tolist(),'triangles':len(faces),'curvedAreaM2':float(area.sum()),'tractionDefinition':'quadrature affine traction fit preserving all six resultant components, consistently integrated with Tri6 shape functions'}


def pipe_patch(points,triangles,request):
    """Smooth compact patch; fit the six-wrench about the common local origin."""
    target=np.asarray(request['load']['wrench']);loads=np.zeros_like(points)
    if np.linalg.norm(target)==0:return loads,dict(resultant=[0.]*6,triangles=0)
    g=request['geometry'];d=np.asarray(g['axis']);normal=np.asarray(g['patchNormal']);width=g['patchWidth'];half=np.deg2rad(g['patchAngleDegrees']/2);ro=request['arms'][0]['outerRadius']
    coords=points[triangles];ax=coords@d;rad=coords-ax[:,:,None]*d
    # Only the physical outer cylindrical wall, never the bore or end faces.
    selected=np.flatnonzero((np.max(abs(np.linalg.norm(rad,axis=2)-ro),axis=1)<2e-6)&(np.min(ax,axis=1)<width/2)&(np.max(ax,axis=1)>-width/2))
    faces=triangles[selected];xi,w=get_quadrature_tri(9);N,grad=tri_shape(xi.T);coords=points[faces]
    x=np.einsum('qn,fni->fqi',N,coords);J=np.einsum('fni,qnj->fqij',coords,grad);area=np.linalg.norm(np.cross(J[:,:,:,0],J[:,:,:,1]),axis=-1)*w
    axial=x@d;r=x-axial[:,:,None]*d;angle=np.arccos(np.clip((r@normal)/np.linalg.norm(r,axis=2),-1,1))
    window=np.where(abs(axial)<width/2,np.cos(np.pi*axial/width)**2,0)*np.where(angle<half,np.cos(np.pi*angle/(2*half))**2,0)
    weight=area*window
    if np.count_nonzero(weight)>5:
        M=np.zeros((*x.shape[:2],6,3));M[:,:,:3,:]=np.eye(3);M[:,:,3:,:]=cross_matrix(x)
        gram=np.einsum('fq,fqij,fqkj->ik',weight,M,M,optimize=True)
        coeff=np.linalg.solve(gram,target);traction=np.einsum('fqij,i->fqj',M,coeff)
        nodal=np.einsum('qn,fq,fqi->fni',N,weight,traction,optimize=True);np.add.at(loads,faces.ravel(),nodal.reshape(-1,3))
    else:raise ValueError('有限加载面片网格太粗，无法保持合力与合矩')
    actual=np.r_[loads.sum(axis=0),np.cross(points,loads).sum(axis=0)]
    np.testing.assert_allclose(actual,target,rtol=1e-8,atol=1e-6)
    return loads,dict(resultant=actual.tolist(),target=target.tolist(),triangles=len(faces),curvedAreaM2=float(np.sum(area*(window>0))),weightedAreaM2=float(weight.sum()),widthM=width,angleDegrees=g['patchAngleDegrees'],tractionDefinition='compact cosine-squared weighting, six-resultant affine traction fit, Tri6 consistent integration; no rigid coupling')
