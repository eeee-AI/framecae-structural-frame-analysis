"""01 section-resultant Neumann submodel; rigid pose is observation only."""
import numpy as np
from scipy.sparse import coo_matrix,diags
from scipy.sparse.linalg import LinearOperator,cg
from skfem.quadrature import get_quadrature_tri
import pyamg
from scipy.linalg import qr
from .boundary import tri_shape,cross_matrix,cut_observations


def surface_operators(points,triangles,center,length=1.):
    """C u = [mean translation, length * mean rotation]; C R = I.

    Rotation is the continuum least-squares swirling measure, integrated on
    the actual curved Tri6 surface. Tractions C.T [F,M/length] do exact work.
    """
    ids=np.unique(triangles);lookup=np.full(len(points),-1,dtype=int);lookup[ids]=np.arange(len(ids))
    local=lookup[triangles];coordinates=points[triangles];xi,w=get_quadrature_tri(5);N,g=tri_shape(xi.T)
    x=np.einsum('qn,fni->fqi',N,coordinates);J=np.einsum('fni,qnj->fqij',coordinates,g)
    area=np.linalg.norm(np.cross(J[:,:,:,0],J[:,:,:,1]),axis=-1)*w
    R=np.concatenate((np.broadcast_to(np.eye(3),(*x.shape[:2],3,3)),-cross_matrix(x-center)/length),axis=-1)
    gram=np.einsum('fq,fqia,fqib->ab',area,R,R,optimize=True)
    integrated=np.einsum('fq,fqia,qn->fani',area,R,N,optimize=True)
    B=np.zeros((6,3*len(ids)))
    for a in range(6):np.add.at(B[a].reshape(-1,3),local.ravel(),integrated[:,a].reshape(-1,3))
    C=np.linalg.solve(gram,B)
    rigid=np.concatenate((np.broadcast_to(np.eye(3),(len(ids),3,3)),-cross_matrix(points[ids]-center)/length),axis=2).reshape(-1,6)
    np.testing.assert_allclose(C@rigid,np.eye(6),rtol=1e-10,atol=1e-10)
    return ids,C,float(area.sum())


def sections(points,triangles,request,cut_sets):
    cuts={};operators=[];rows=[];cols=[];values=[];motions=[];cut_load=np.zeros_like(points)
    for index,arm in enumerate(request['arms']):
        key=str(arm['element']);ids=np.asarray(cut_sets[key]);mask=np.zeros(len(points),dtype=bool);mask[ids]=True
        tri=triangles[np.all(mask[triangles],axis=1)]
        if len(tri)<2:raise ValueError('Missing element-based annular cut E'+key)
        length=arm['outerRadius'];ids,C,area=surface_operators(points,tri,np.array(arm['center']),length)
        cuts[key]=ids;dofs=(ids[:,None]*3+np.arange(3)).ravel()
        ri,ci=np.indices(C.shape);rows.extend((ri+6*index).ravel());cols.extend(dofs[ci].ravel());values.extend(C.ravel())
        motion=np.r_[arm['translation'],np.array(arm['rotation'])*length];motions.extend(motion)
        wrench=np.asarray(arm['beamCutWrench']);nodal=(C.T@np.r_[wrench[:3],wrench[3:]/length]).reshape(-1,3)
        shear_transfer=None
        if request.get('couplingMode')=='forceSubmodel' and request.get('shearDistribution','resultantAffine')=='saintVenantAnnulus':
            from .saint_venant import replace_shear
            nodal,shear_transfer=replace_shear(points,tri,arm,request['material']['nu'],ids,C,nodal)
        np.add.at(cut_load,ids,nodal)
        actual=np.r_[nodal.sum(axis=0),np.cross(points[ids]-arm['center'],nodal).sum(axis=0)]
        np.testing.assert_allclose(actual,wrench,rtol=1e-9,atol=1e-7)
        operators.append(dict(element=arm['element'],ids=ids,C=C,length=length,area=area,sourceWrench=wrench.tolist(),shearTransfer=shear_transfer))
    matrix=coo_matrix((values,(rows,cols)),shape=(6*len(operators),3*len(points))).tocsr();matrix.eliminate_zeros()
    return cuts,matrix,np.array(motions),cut_load,operators


def slender_modes(points,request):
    """AMG candidates for branch bending/twist; they impose no model BCs."""
    extra=[];hub=request['geometry']['hubRadius']
    for arm in request['arms']:
        d=np.array(arm['direction']);axial=points@d;r=points-axial[:,None]*d
        start=.65*hub;span=arm['length']-start;s=np.maximum((axial-start)/span,0)
        # Branches are separated outside the sphere; a smooth radial cutoff
        # keeps candidate fields from spreading into a different pipe.
        taper=np.exp(-np.maximum(np.linalg.norm(r,axis=1)/(1.15*arm['outerRadius'])-1,0)**2*12)
        axis=np.eye(3)[np.argmin(abs(d))];axis-=d*(axis@d);axis/=np.linalg.norm(axis)
        for e in [axis,np.cross(d,axis)]:
            for power in [2,3]:
                value=s[:,None]**power*e-power*s[:,None]**(power-1)/span*(r@e)[:,None]*d
                extra.append((value*taper[:,None]).ravel())
        extra.append((s[:,None]*d*taper[:,None]).ravel())
        extra.append((s[:,None]*np.cross(d,r)*taper[:,None]).ravel())
    return np.column_stack(extra)


def projected_solve(K,points,loads,progress=None,initial=None,extra_modes=None,connectivity=None):
    """Exact orthogonal projection, not a penalty enforcement approximation."""
    progress=progress or (lambda *a,**k:None)
    scale=1/np.sqrt(K.diagonal());A=(diags(scale)@K@diags(scale)).tobsr(blocksize=(3,3))
    rigid=np.concatenate((np.broadcast_to(np.eye(3),(len(points),3,3)),-cross_matrix(points)),axis=2).reshape(-1,6)
    modes=rigid/scale[:,None]
    Q=np.linalg.qr(modes,mode='reduced')[0]
    def normal(v):return Q@(Q.T@v)
    u0=np.zeros(K.shape[0])
    def project(v):return v-normal(v)
    rhs=project(scale*loads.ravel()-A@u0)
    operator=LinearOperator(A.shape,matvec=lambda v:project(A@project(v))+normal(v),dtype=float)
    progress('preconditioning');print('SUBMODEL_AMG_SETUP',A.shape,A.nnz,flush=True)
    # Six pins regularize only the AMG preconditioner; not physical BCs.
    pivots=qr(modes.T,mode='economic',pivoting=True)[2][:6];pins=np.zeros(A.shape[0]);pins[pivots]=1.
    amg_matrix=(A+diags(pins)).tobsr(blocksize=(3,3))
    candidates=modes if extra_modes is None else np.column_stack([modes,extra_modes/scale[:,None]])
    candidates/=np.maximum(np.linalg.norm(candidates,axis=0),1e-30)
    print('SUBMODEL_AMG_CANDIDATES',candidates.shape[1],flush=True)
    # PyAMG counts block nodes here, not scalar DOFs. With 18 candidates,
    # max_coarse=250 permits a 4500 x 4500 dense SVD on the coarsest grid.
    # Keep the dense problem small without changing K, loads or CG tolerance.
    if connectivity is not None:
        from .p_preconditioner import build
        ml=build(amg_matrix,points,connectivity,scale,candidates)
    else:
        ml=pyamg.smoothed_aggregation_solver(amg_matrix,B=candidates,symmetry='symmetric',max_levels=12,max_coarse=max(5,240//candidates.shape[1]),coarse_solver='pinv',
            presmoother=('block_gauss_seidel',{'sweep':'symmetric'}),postsmoother=('block_gauss_seidel',{'sweep':'symmetric'}))
    print('AMG_LEVELS',len(ml.levels),'COARSE_SCALAR_DOFS',ml.levels[-1].A.shape[0],flush=True)
    M=ml.aspreconditioner();pre=LinearOperator(A.shape,matvec=lambda v:project(M@project(v))+normal(v),dtype=float)
    iterations=[0];progress('solving')
    def callback(v):
        iterations[0]+=1
        if iterations[0]%20==1:
            residual=float(np.linalg.norm(operator@v-rhs)/max(np.linalg.norm(rhs),1e-30));print('SUBMODEL_CG',iterations[0],residual,flush=True);progress('solving',iteration=iterations[0],residual=residual)
    x0=project(initial.ravel()/scale-u0) if initial is not None else None
    x,info=cg(operator,rhs,x0=x0,M=pre,rtol=2e-11,atol=1e-15,maxiter=2200,callback=callback)
    u=scale*(u0+project(x));r=K@u-loads.ravel()
    residual=float(np.linalg.norm(project(scale*r))/max(np.linalg.norm(scale*loads.ravel()),np.linalg.norm(rhs),1e-30))
    if info or residual>1e-9:raise ValueError('Submodel projected solve failed: info=%s, residual=%.4g'%(info,residual))
    physical=float(np.linalg.norm(r)/max(np.linalg.norm(loads),1.))
    if physical>1e-8:raise ValueError('Unbalanced Neumann data or unresolved solve: %.4g'%physical)
    return u.reshape(-1,3),iterations[0],residual


def solve(K,points,triangles,loads,request,cut_sets,progress,initial=None,connectivity=None):
    if request.get('couplingMode')!='forceSubmodel':raise ValueError('Only section-resultant loading is supported')
    mode='forceSubmodel';cuts,C,q,cut_load,operators=sections(points,triangles,request,cut_sets)
    _,_,_,rigid,gauge=cut_observations(points,request,cut_sets)
    external=loads.copy()
    initial=initial-rigid if initial is not None else None
    extra=slender_modes(points,request)
    if extra is not None and initial is not None and np.linalg.norm(initial)>1e-20:extra=np.column_stack([extra,initial.ravel()])
    if mode=='forceSubmodel':
        external+=cut_load
        if request.get('analysisType')=='idealClamp':
            return clamped_solve(K,points,loads,external,request,cuts,operators,progress,connectivity)
        resultant=np.r_[external.sum(axis=0),np.cross(points,external).sum(axis=0)]
        force_scale=max(sum(np.linalg.norm(a['beamCutWrench'][:3]) for a in request['arms']),np.linalg.norm(loads),1.)
        length=max(a['length'] for a in request['arms'])
        if np.linalg.norm(resultant[:3])/force_scale>1e-8 or np.linalg.norm(resultant[3:])/(force_scale*length)>1e-8:
            raise ValueError('01 cut forces plus retained loads do not balance: '+str(resultant.tolist())+'; force submodel cannot hide unmatched loads or node self-weight.')
        elastic,count,residual=projected_solve(K,points,external,progress=progress,initial=initial,extra_modes=extra,connectivity=connectivity)
        boundary_error=0.;definition='01 section resultants -> consistent Tri6 surface tractions; 01 motion fixes rigid pose only'
    u=elastic+rigid;reaction=(K@elastic.ravel()-loads.ravel()).reshape(-1,3)
    records=[]
    for op in operators:
        arm=next(a for a in request['arms'] if a['element']==op['element']);ids=op['ids'];motion=op['C']@u[ids].ravel()
        rigid_values=np.array(arm['translation'])+np.cross(np.array(arm['rotation']),points[ids]-arm['center'])
        records.append(dict(element=arm['element'],sourceTranslation=arm['translation'],sourceRotation=arm['rotation'],
            actualTranslation=motion[:3].tolist(),actualRotation=(motion[3:]/op['length']).tolist(),
            averageMotionErrorM=float(np.max(abs(motion-np.r_[arm['translation'],np.array(arm['rotation'])*op['length']]))),
            deviationFromBeamSectionMotionM=float(np.max(abs(u[ids]-rigid_values))),areaM2=op['area']))
        if op.get('shearTransfer') is not None:records[-1]['shearTransfer']=op['shearTransfer']
    details=dict(method=mode,definition=definition,usesAbaqus=False,parentSource=request['globalSolutionAudit'],
        imposesAllCutNodeDisplacements=False,updatesParentModel=False,appliedCutTractions=mode=='forceSubmodel',
        imposedMeanMotion=False,boundaryTransferErrorM=boundary_error,cuts=records,
        primarySource='01 section resultants',
        validity='Parent boundary accuracy must be assessed; neither choice corrects the parent stiffness.')
    if mode=='forceSubmodel':details['shearDistribution']=request.get('shearDistribution','resultantAffine')
    return u,reaction,rigid,gauge,count,residual,cuts,external,details


def clamped_solve(K,points,retained,external,request,cuts,operators,progress,connectivity=None):
    from .tet10 import free_block_matrix
    d=np.asarray(request['geometry']['axis']);ro=request['arms'][0]['outerRadius'];ri=request['arms'][0]['innerRadius']
    axial=points@d;radius=np.linalg.norm(points-axial[:,None]*d,axis=1)
    fixed=np.flatnonzero((abs(axial)<1e-8)&(radius>=ri-1e-7)&(radius<=ro+1e-7));free=np.setdiff1d(np.arange(len(points)),fixed)
    if len(fixed)<6:raise ValueError('理想固定端节点集缺失')
    A=free_block_matrix(K,free);scale=1/np.sqrt(A.diagonal());A=(diags(scale)@A@diags(scale)).tobsr(blocksize=(3,3));rhs=scale*external[free].ravel()
    rigid=np.concatenate((np.broadcast_to(np.eye(3),(len(free),3,3)),-cross_matrix(points[free])),axis=2).reshape(-1,6)
    candidates=np.c_[rigid,slender_modes(points,request)[np.repeat(free*3,3)+np.tile(np.arange(3),len(free))]]/scale[:,None]
    candidates/=np.maximum(np.linalg.norm(candidates,axis=0),1e-30)
    progress('preconditioning')
    if connectivity is not None:
        from .p_preconditioner import build
        ml=build(A,points,connectivity,scale,candidates,free)
    else:ml=pyamg.smoothed_aggregation_solver(A,B=candidates,symmetry='symmetric',max_levels=12,max_coarse=max(5,240//candidates.shape[1]),coarse_solver='pinv',presmoother=('block_gauss_seidel',{'sweep':'symmetric'}),postsmoother=('block_gauss_seidel',{'sweep':'symmetric'}))
    print('CLAMP_AMG_LEVELS',len(ml.levels),'COARSE_SCALAR_DOFS',ml.levels[-1].A.shape[0],flush=True)
    count=[0];progress('solving')
    def step(v):
        count[0]+=1
        if count[0]%20==1:progress('solving',iteration=count[0]);print('CLAMP_CG',count[0],flush=True)
    x,info=cg(A,rhs,M=ml.aspreconditioner(),rtol=2e-11,atol=1e-15,maxiter=2200,callback=step)
    u=np.zeros_like(points);u[free]=(scale*x).reshape(-1,3)
    residual_vector=(K@u.ravel()).reshape(-1,3)-external
    relative=float(np.linalg.norm(residual_vector[free])/max(np.linalg.norm(external[free]),1.))
    if info or relative>1e-8:raise ValueError(f'Ideal clamp solve failed: {info}, {relative}')
    reaction=(K@u.ravel()).reshape(-1,3)-retained
    support=residual_vector[fixed];wrench=np.r_[support.sum(axis=0),np.cross(points[fixed],support).sum(axis=0)]
    expected=np.asarray(request['supportExpected']);delta=wrench-expected
    check=dict(actual=wrench.tolist(),expected=expected.tolist(),forceRelativeDifference=float(np.linalg.norm(delta[:3])/max(np.linalg.norm(expected[:3]),1.)),momentRelativeDifference=float(np.linalg.norm(delta[3:])/max(np.linalg.norm(expected[3:]),1.)),fixedNodeCount=len(fixed),maximumFixedDisplacementM=float(abs(u[fixed]).max()))
    if max(check['forceRelativeDifference'],check['momentRelativeDifference'])>1e-5:raise ValueError('实体理想支座反力与01不一致: '+str(check))
    records=[]
    for op in operators:
        motion=op['C']@u[op['ids']].ravel();records.append(dict(element=op['element'],actualTranslation=motion[:3].tolist(),actualRotation=(motion[3:]/op['length']).tolist(),areaM2=op['area']))
    details=dict(method='forceSubmodel',definition='01 cut tractions + physical ideal clamped annular face',primarySource='01 section resultants',boundaryTransferErrorM=0.,cuts=records,support=check,imposesAllCutNodeDisplacements=False,updatesParentModel=False,usesAbaqus=False)
    return u,reaction,np.zeros_like(points),np.zeros(6),count[0],relative,cuts,external,details
