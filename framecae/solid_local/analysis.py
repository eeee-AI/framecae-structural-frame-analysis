"""Standalone sparse linear solve, residual checks, stress and native exports."""
import gc,json,time
from pathlib import Path
import numpy as np
from scipy.sparse.linalg import cg,LinearOperator,spsolve
import pyamg
from .tet10 import assemble,free_block_matrix,constitutive,evaluate_stress,mises,REFERENCE_NODES,body_force
from .boundary import cut_observations,load_cap,cross_matrix


def solve(directory,request,progress=None):
    if request.get('couplingMode')!='forceSubmodel':raise ValueError('本发行版只支持01截面内力驱动。')
    directory=Path(directory);started=time.time()
    progress=progress or (lambda stage,**info:None)
    reference_length=max(float(a['length']) for a in request['arms'])
    with np.load(directory/'mesh.npz') as z:
        points=z['points'];cells=z['tetra10'];faces=z['triangle6']
        cut_sets={str(a['element']):z['cut_E'+str(a['element'])] for a in request['arms']} if all('cut_E'+str(a['element']) in z for a in request['arms']) else None
    # Older mesh caches can contain construction points; reject rather than hiding a singularity.
    if len(np.unique(cells))!=len(points):raise ValueError('Unused mesh nodes; regenerate geometry')
    D=constitutive(request['material']['E'],request['material']['nu'])
    def assembly_progress(n,total):
        print('ASSEMBLY',n,total,flush=True);progress('assembling',done=n,total=total)
    K,volumes=assemble(points,cells,D,assembly_progress)
    assembly_time=time.time()-started
    nonzeros=K.nnz
    print('ASSEMBLY_DONE',round(assembly_time,2),'seconds; scalar storage entries',nonzeros,flush=True)
    loads,cap=load_cap(points,faces,request)
    cap_loads=loads.copy()
    gravity=np.asarray(request.get('gravity',[0,0,0]))
    # Force submodels inherit the ideal-beam line mass, not extra solid hub mass.
    gravity_loads=body_force(points,cells,request['material']['density']*gravity) if not request.get('memberLoadMapping') else np.zeros_like(points)
    loads+=gravity_loads
    from .member_loading import equivalent_loads
    member_loads,member_load_transfer=equivalent_loads(points,cells,request)
    loads+=member_loads
    if member_load_transfer:
        (directory/'member_load_transfer.json').write_text(json.dumps(member_load_transfer,ensure_ascii=False,indent=2),encoding='utf-8')
        print('MEMBER_LOAD_TRANSFER',json.dumps(member_load_transfer),flush=True)
    coupling_details=None;submodel_details=None;external_loads=loads
    if request.get('couplingMode')=='forceSubmodel':
        from .submodel import solve as solve_submodel
        initial=None
        if (directory/'status.json').exists():
            prior=json.loads((directory/'status.json').read_text('utf-8')).get('meshReusedFrom')
            if request.get('shearDistribution')=='saintVenantAnnulus':
                from .service import physical_key
                baseline={**request,'shearDistribution':'resultantAffine'};wanted=physical_key(baseline)
                for candidate in directory.parent.iterdir():
                    if candidate==directory or not (candidate/'solution.npz').exists() or not (candidate/'local_request.json').exists():continue
                    try:
                        old_q=json.loads((candidate/'local_request.json').read_text('utf-8'))
                        if physical_key(old_q)==wanted:prior=candidate.name;break
                    except (OSError,ValueError,KeyError):continue
            if prior and (directory.parent/prior/'solution.npz').exists():
                with np.load(directory.parent/prior/'solution.npz') as old:
                    if old['displacement'].shape==points.shape:initial=old['displacement']
                if initial is not None:print('INITIAL_GUESS_ONLY',prior,flush=True)
        if request.get('settingsSnapshot',{}).get('disableInitialGuess'):initial=None
        # Same-mesh B-joint and ideal-clamp regressions preserve strains and
        # energy to <1e-10. Auxiliary space affects only the preconditioner.
        use_auxiliary=request.get('settingsSnapshot',{}).get('preconditioner','pCoarseAMG')=='pCoarseAMG'
        u,reaction,rigid,gauge,count,relative,cuts,external_loads,submodel_details=solve_submodel(K,points,faces,loads,request,cut_sets,progress,initial,connectivity=cells if use_auxiliary else None)
        w=(u-rigid).ravel();history=[0]*count;pre_time=0.
        _,fixed,values,_,_=cut_observations(points,request,cut_sets)
        fixed_nodes=np.unique(fixed//3);free=np.arange(K.shape[0]-6)
        if request.get('analysisType')=='idealClamp':
            # Residual reaction contains cut tractions plus the physical support.
            d=np.asarray(request['geometry']['axis']);support_nodes=np.flatnonzero(abs(points@d)<1e-8)
            fixed_nodes=np.union1d(fixed_nodes,support_nodes);free=np.arange(3*(len(points)-len(support_nodes)))
        (directory/'submodel.json').write_text(json.dumps(submodel_details,ensure_ascii=False,indent=2),encoding='utf-8')
    cut_records=[]
    for arm in request['arms']:
        ids=cuts[str(arm['element'])];c=np.asarray(arm['center']);rf=reaction[ids]
        wrench=np.r_[rf.sum(axis=0),np.cross(points[ids]-c,rf).sum(axis=0)]
        actual_u=u[ids];expected_u=np.asarray(arm['translation'])+np.cross(np.asarray(arm['rotation']),points[ids]-c)
        A=np.concatenate((np.broadcast_to(np.eye(3),(len(ids),3,3)),-cross_matrix(points[ids]-c)),axis=2).reshape(-1,6)
        recovered=np.linalg.lstsq(A,actual_u.ravel(),rcond=None)[0]
        if submodel_details:
            record=next(c for c in submodel_details['cuts'] if c['element']==arm['element'])
            recovered=np.r_[record['actualTranslation'],record['actualRotation']]
        cut_records.append({'element':arm['element'],'wrenchAtCutCenter':wrench.tolist(),'beamExpected':arm['beamCutWrench'],'originalBeamExpected':arm.get('originalBeamCutWrench',arm['beamCutWrench']),
            'nodeCount':len(ids),'prescribedTranslation':arm['translation'],'prescribedRotation':arm['rotation'],
            'recoveredTranslation':recovered[:3].tolist(),'recoveredRotation':recovered[3:].tolist(),
            'maximumDisplacementErrorM':float(np.max(abs(actual_u-expected_u)))})
    scale=max(np.linalg.norm(request['load']['wrench'][:3]),max(np.linalg.norm(c['wrenchAtCutCenter'][:3]) for c in cut_records),1.)
    rf=np.r_[reaction[fixed_nodes].sum(axis=0),np.cross(points[fixed_nodes],reaction[fixed_nodes]).sum(axis=0)]
    applied=np.r_[loads.sum(axis=0),np.cross(points,loads).sum(axis=0)];balance=rf+applied
    if np.linalg.norm(balance[:3])/scale>1e-5 or np.linalg.norm(balance[3:])/(scale*reference_length)>1e-5:raise ValueError('Force/moment balance failed')
    energy=float(.5*w@(K@w));del K;gc.collect()
    progress('recovering')
    element_nodal=np.empty((len(cells),10,6),dtype=np.float32);stress_centroid=np.empty((len(cells),6),dtype=np.float32)
    nodal_sum=np.zeros((len(points),6));nodal_weight=np.zeros(len(points))
    for start in range(0,len(cells),1024):
        end=min(start+1024,len(cells));conn=cells[start:end]
        stress=evaluate_stress(points[conn],w.reshape(-1,3)[conn],D,REFERENCE_NODES)
        element_nodal[start:end]=stress
        stress_centroid[start:end]=evaluate_stress(points[conn],w.reshape(-1,3)[conn],D,[[.25,.25,.25]])[:,0]
        for j in range(10):
            np.add.at(nodal_sum,conn[:,j],stress[:,j]*volumes[start:end,None]);np.add.at(nodal_weight,conn[:,j],volumes[start:end])
    nodal_stress=nodal_sum/nodal_weight[:,None];nodal_vm=mises(nodal_stress)
    np.savez_compressed(directory/'solution.npz',displacement=u,elastic_displacement=w.reshape(-1,3),reaction=reaction,
        loads=external_loads,element_nodal_stress=element_nodal,centroid_stress=stress_centroid,nodal_stress=nodal_stress,
        nodal_mises=nodal_vm,element_volumes=volumes)
    meta=json.loads((directory/'mesh_meta.json').read_text('utf-8'))
    result={'solver':'standalone curved isoparametric Tet10, NumPy/SciPy/pyamg; no Abaqus solve',
      'stressOrder':['S11','S22','S33','S12','S13','S23'],'strainConvention':'engineering shear',
      'preconditioner':'pCoarseAMG' if use_auxiliary else 'standardAMG',
      'nodes':len(points),'elements':len(cells),'freeDofs':len(free),'nnz':nonzeros,'iterations':len(history),'relativeResidual':relative,
      'forceBalanceRelativeError':float(np.linalg.norm(balance[:3])/scale),'momentBalanceRelativeError':float(np.linalg.norm(balance[3:])/(scale*reference_length)),
      'cutDisplacementMaxErrorM':submodel_details['boundaryTransferErrorM'],
      'reactionAtNode':rf.tolist(),'appliedAtNode':applied.tolist(),'cutResultants':cut_records,
      'coupling':coupling_details,'submodel':submodel_details,'gaugeRigidMotion':gauge.tolist(),'cap':cap,'bodyForceResultant':np.r_[gravity_loads.sum(axis=0),np.cross(points,gravity_loads).sum(axis=0)].tolist(),'strainEnergyJ':energy,'volumeM3':float(volumes.sum()),
      'cadVolumeRelativeError':float(abs(volumes.sum()-meta['cadVolumeM3'])/meta['cadVolumeM3']),
      'maximumNodalAveragedMisesPa':float(nodal_vm.max()),'maximumElementNodalMisesPa':float(mises(element_nodal).max()),
      'timing':{'assemblySeconds':assembly_time,'amgSetupSeconds':pre_time,'totalSeconds':time.time()-started},
      'node':request['node'],'cutLengthM':reference_length,'cutLengthsM':{str(a['element']):a['length'] for a in request['arms']},'toeSizeM':meta['toeSize'],'convergence':'not yet compared','globalLocalTransmission':'01 section-resultant loading; Saint-Venant shear'}
    if submodel_details:result['globalLocalTransmission']=submodel_details['definition']
    if member_load_transfer:result['memberLoadTransfer']=member_load_transfer
    (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
    return result
