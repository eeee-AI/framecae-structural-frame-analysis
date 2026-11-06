# -*- coding: utf-8 -*-
"""Abaqus Python ODB extraction; no CAE license or project imports required."""
import csv
import json
from pathlib import Path
import sys
import numpy as np
from odbAccess import openOdb
from abaqusConstants import ELEMENT_NODAL


def mises(s):
    a,b,c,d,e,f=np.asarray(s).T
    return np.sqrt(((a-b)**2+(b-c)**2+(c-a)**2)/2+3*(d*d+e*e+f*f))


def extract(filename):
    folder=Path(filename).resolve().parent
    req=json.loads((folder/'local_request.json').read_text('utf-8'))
    mesh=json.loads((folder/'mesh.json').read_text('utf-8'))
    meta=json.loads((folder/'mesh_meta.json').read_text('utf-8'))
    points=np.array(mesh['nodes']);elements=np.array(mesh['elements']);n=len(points);ne=len(elements)
    odb=openOdb(path=str(Path(filename).resolve()),readOnly=True)
    try:
        frame=odb.steps['STATIC'].frames[-1]
        if frame.frameValue<.999999: raise RuntimeError('Incomplete final frame')
        displacement=np.zeros((n,3));reaction=np.zeros((n,3))
        for value in frame.fieldOutputs['U'].values:
            if value.nodeLabel<=n:displacement[value.nodeLabel-1]=value.data
        for value in frame.fieldOutputs['RF'].values:
            if value.nodeLabel<=n:reaction[value.nodeLabel-1]=value.data
        volumes={}
        if 'IVOL' in frame.fieldOutputs:
            volumes={(v.elementLabel,v.integrationPoint):float(v.data) for v in frame.fieldOutputs['IVOL'].values}
        tensor=np.zeros((ne,6));weight=np.zeros(ne);ipmax=np.zeros(ne)
        for value in frame.fieldOutputs['S'].values:
            i=value.elementLabel-1;w=volumes.get((value.elementLabel,value.integrationPoint),1.)
            tensor[i]+=np.array(value.data)*w;weight[i]+=w
            ipmax[i]=max(ipmax[i],float(value.mises))
        tensor/=weight[:,None]
        if not volumes:
            raise RuntimeError('IVOL is required for physical region weighting')
        vm=mises(tensor)
        nodal_tensor=np.zeros((n,6));nodal_weight=np.zeros(n)
        for j in range(elements.shape[1]):
            np.add.at(nodal_tensor,elements[:,j],tensor*weight[:,None])
            np.add.at(nodal_weight,elements[:,j],weight)
        nodal_tensor/=np.maximum(nodal_weight[:,None],1e-30)
        nodal_vm=mises(nodal_tensor)
        faces=np.array(meta['faces']);owners=np.array(meta['faceOwners'])
        face_vm=nodal_vm[faces].mean(axis=1)
        centers=points[elements].mean(axis=1)
        initial=odb.steps['STATIC'].frames[0]
        if initial.frameValue==0 and 'COORD' in initial.fieldOutputs:
            coordinate_sum=np.zeros((ne,3));coordinate_weight=np.zeros(ne)
            for value in initial.fieldOutputs['COORD'].values:
                i=value.elementLabel-1;w=volumes.get((value.elementLabel,value.integrationPoint),0.)
                coordinate_sum[i]+=np.asarray(value.data)*w;coordinate_weight[i]+=w
            if np.any(coordinate_weight<=0):raise RuntimeError('Integration-point coordinate weights missing')
            centers=coordinate_sum/coordinate_weight[:,None]
        elif np.linalg.norm(req['gravity']):
            raise RuntimeError('Gravity moment validation requires COORD integration-point output')
        gravity=np.array(req['gravity']);body_forces=weight[:,None]*req['material']['density']*gravity
        body_force=body_forces.sum(axis=0);body_moment=np.cross(centers,body_forces).sum(axis=0)
        applied=np.asarray(req['load']['wrench'])+np.r_[body_force,body_moment]
        rf_total=np.r_[reaction.sum(axis=0),np.cross(points,reaction).sum(axis=0)]
        residual=rf_total+applied
        # A node without direct external load still has self-equilibrated cut
        # reactions. Use their resultant scale rather than dividing by 1 N.
        cut_force_scale=max(np.linalg.norm(reaction[np.asarray(ids,dtype=int)].sum(axis=0))
                            for ids in meta['cuts'].values())
        scale=max(np.linalg.norm(applied[:3]),cut_force_scale,1.)
        force_error=float(np.linalg.norm(residual[:3])/scale)
        moment_error=float(np.linalg.norm(residual[3:])/max(scale*req['geometry']['hubRadius'],np.linalg.norm(applied[3:]),1.))
        cut_comparisons=[]
        for arm in req['arms']:
            ids=np.array(meta['cuts'][str(arm['element'])]);c=np.array(arm['center'])
            wrench=np.r_[reaction[ids].sum(axis=0),np.cross(points[ids]-c,reaction[ids]).sum(axis=0)]
            expected=np.array(arm['beamCutWrench'])
            cut_comparisons.append({'element':arm['element'],'solidReaction':wrench.tolist(),'beamExpected':expected.tolist(),
                'forceAbsoluteDifference':float(np.linalg.norm(wrench[:3]-expected[:3])),
                'momentAbsoluteDifference':float(np.linalg.norm(wrench[3:]-expected[3:])),
                'forceRelativeDifference':float(np.linalg.norm(wrench[:3]-expected[:3])/max(np.linalg.norm(expected[:3]),1.)),
                'momentRelativeDifference':float(np.linalg.norm(wrench[3:]-expected[3:])/max(np.linalg.norm(expected[3:]),1.))})
        boundary_error=0.
        for key,value in meta['prescribed'].items():
            boundary_error=max(boundary_error,float(np.linalg.norm(displacement[int(key)]-value)))
        regions={}
        for name,indices in meta['regions'].items():
            if not indices: continue
            ids=np.array(indices);peak=ids[np.argmax(ipmax[ids])]
            regions[name]={'elementCount':len(ids),'volume':float(weight[ids].sum()),
                'volumeMeanElementMises':float(np.average(vm[ids],weights=weight[ids])),
                'maxIntegrationPointMises':float(ipmax[peak]),'peakElement':int(peak+1),'peakLocation':centers[peak].tolist()}
        max_id=int(np.argmax(vm));nodal_id=int(np.argmax(nodal_vm))
        nominal=max(abs(a['nominalStress']) for a in req['arms'])
        boundary_ids=np.unique(faces)
        # Keep Abaqus' one-sided element-nodal extrapolation. A fixed physical
        # weld-toe path is sampled later without averaging neighbouring elements.
        if req['mesh'].get('toeSize'):
            element_nodal=np.empty((ne,elements.shape[1],6),dtype=np.float32)
            seen=np.zeros(ne,dtype=bool)
            extrapolated=frame.fieldOutputs['S'].getSubset(position=ELEMENT_NODAL,readOnly=True)
            for block in extrapolated.bulkDataBlocks:
                labels=np.asarray(block.elementLabels,dtype=int).reshape(-1,10)[:,0]-1
                labels_nodes=np.asarray(block.nodeLabels,dtype=int).reshape(-1,10)-1
                if not np.array_equal(labels_nodes,elements[labels]):raise RuntimeError('Element-nodal connectivity order mismatch')
                element_nodal[labels]=np.asarray(block.data,dtype=np.float32).reshape(-1,10,6);seen[labels]=True
            if not seen.all():raise RuntimeError('Missing element-nodal stress values')
            local_indices=np.argmax(elements[owners,None,:]==faces[:,:,None],axis=2)
            surface_tensor=element_nodal[owners[:,None],local_indices]
            np.savez_compressed(str(folder/'toe_fields.npz'),points=points,faces=faces,owners=owners,
                                surfaceTensor=surface_tensor)
        near_cut=np.array([any(abs(points[i]@np.array(a['direction'])-a['length'])<2*req['mesh']['size'] for a in req['arms']) for i in boundary_ids])
        result={'node':req['node'],'connectedElements':[a['element'] for a in req['arms']],
            'elementType':mesh['elementType'],'nodeCount':n,'elementCount':ne,'faceCount':len(faces),
            'freeDofCount':3*(n-len(meta['prescribed'])),'solutionMethod':'Abaqus/Standard',
            'actualMeshSize':req['mesh']['size'],'localMeshSize':mesh.get('effectiveFocusSize',req['mesh']['focusSize']),
            'nominalStress':nominal,'maximumVonMises':float(vm.max()),'maximumIntegrationPointVonMises':float(ipmax.max()),
            'maximumNodalVonMises':float(nodal_vm.max()),'maximumPrincipalStress':float(np.max(np.linalg.eigvalsh(np.array([
                [[a,d,e],[d,b,f],[e,f,c]] for a,b,c,d,e,f in tensor])))),
            'maximumLocationLocal':centers[max_id].tolist(),'maximumNodalLocation':points[nodal_id].tolist(),
            'maximumLocationGlobal':(centers[max_id]+np.array(req['origin'])).tolist(),
            'stressConcentrationFactor':float(vm.max()/max(nominal,1e-30)),
            'smoothedStressConcentrationFactor':float(nodal_vm.max()/max(nominal,1e-30)),
            'maximumDisplacement':float(np.linalg.norm(displacement,axis=1).max()),
            'regions':regions,'convergenceStatus':'not_checked','cutBoundaryNodeCount':int(near_cut.sum())}
        result['toeMeshSize']=mesh.get('effectiveToeSize',req['mesh'].get('toeSize'))
        validation={'forceBalanceRelativeError':force_error,'momentBalanceRelativeError':moment_error,
                    'forceBalanceAbsoluteError':float(np.linalg.norm(residual[:3])),
                    'momentBalanceAbsoluteError':float(np.linalg.norm(residual[3:])),
                    'forceBalanceReferenceScale':float(scale),
                    'cutDisplacementMaxError':boundary_error,'reactionWrench':rf_total.tolist(),
                    'appliedWrenchIncludingGravity':applied.tolist(),'cutComparisons':cut_comparisons,
                    'loadRecoveredWrench':meta['recoveredWrench'],
                    'loadTransfer':meta.get('loadTransfer','equivalentNodalForces'),
                    'cutAreas':meta.get('cutAreas',{}),
                    'forceBalancePassed':force_error<1e-5 and moment_error<1e-5,
                    'meshConvergence':'not_checked','cutLengthSensitivity':'not_checked'}
        weld_indices=set(i for name,ids in meta['regions'].items() if name.startswith('WELD') for i in ids)
        surface_map=np.full(n,-1,dtype=int);surface_map[boundary_ids]=np.arange(len(boundary_ids))
        answer={'schemaVersion':req.get('schemaVersion',1),'kind':'abaqusIntegralHub','fingerprint':req['fingerprint'],'node':req['node'],
            'mesh':{'nodes':points[boundary_ids].tolist(),'faces':surface_map[faces].tolist(),'faceVonMises':face_vm.tolist(),
                    'surfaceNodeLabels':(boundary_ids+1).tolist(),
                    'nodalVonMises':nodal_vm[boundary_ids].tolist(),'displacements':displacement[boundary_ids].tolist(),
                    'weldFaces':[i for i,owner in enumerate(owners) if int(owner) in weld_indices]},
            'tubeArms':req['arms'],'result':result,'validation':validation,'warnings':req['warnings'],
            'connection':{'type':'integralHubRingButtWeld','continuousAllAround':True,'fullPenetration':True,
                          'geometry':req['geometry'],'geometryChecks':{'surfaceFitted':True,'allHex8':False}},
            'meshQuality':mesh.get('meshQuality',{}),
            'geometryPrecheck':req.get('geometryPrecheck'),
            'geometryAudit':mesh.get('geometryAudit',{}),'sectionAudit':req.get('sectionAudit',{}),
            'meshingAttempts':mesh.get('meshingAttempts',[]),
            'regionAssignment':mesh.get('regionAssignment','element centroid axial bands'),
            'stressDefinition':'Integration-point S retained in ODB; element tensors IVOL-weighted; display nodes volume-averaged tensor then Mises. Region means are not weld hot-spot or fatigue stress.'}
        (folder/'local_results.json').write_text(json.dumps(answer,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        (folder/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
        with (folder/'stress.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['element','s11','s22','s33','s12','s13','s23','mises_of_mean','max_ip_mises','volume'])
            writer.writerows([i+1,*tensor[i],vm[i],ipmax[i],weight[i]] for i in range(ne))
        with (folder/'displacement.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['node','ux','uy','uz','rfx','rfy','rfz'])
            writer.writerows([i+1,*displacement[i],*reaction[i]] for i in range(n))
        print('EXTRACT_OK nodes=%d elements=%d balance=%.3g'%(n,ne,force_error))
    finally: odb.close()


if __name__=='__main__': extract(sys.argv[-1])
