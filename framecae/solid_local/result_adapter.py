"""Result contract shared by FrameCAE 03; full fields remain in NPZ/VTU."""
import json,csv
from pathlib import Path
import numpy as np
from .tet10 import shape,mises

def adapt(directory,request,job_id):
    directory=Path(directory);raw=json.loads((directory/'result.json').read_text('utf-8'))
    meta=json.loads((directory/'mesh_meta.json').read_text('utf-8'))
    toes=json.loads((directory/'toe_results.json').read_text('utf-8'))
    shoulders=json.loads((directory/'shoulder_results.json').read_text('utf-8')) if (directory/'shoulder_results.json').exists() else {}
    mesh=np.load(directory/'mesh.npz');solution=np.load(directory/'solution.npz')
    points=mesh['points'];cells=mesh['tetra10'];tri=mesh['triangle6'];boundary=np.unique(tri)
    mapping=np.full(len(points),-1,dtype=np.int32);mapping[boundary]=np.arange(len(boundary));tri6=mapping[tri]
    faces=np.concatenate([tri6[:,idx] for idx in ([0,3,5],[3,1,4],[5,4,2],[3,4,5])])
    nodal_mises=solution['nodal_mises'];cloud=nodal_mises[boundary];u=solution['displacement'][boundary]
    N,_=shape([[.25,.25,.25]]);centers=np.einsum('n,eni->ei',N[0],points[cells]);stress=mises(solution['centroid_stress']);volume=solution['element_volumes']
    def region(mask):
        return dict(elements=int(mask.sum()),meanMisesPa=float(np.average(stress[mask],weights=volume[mask])) if mask.any() else None,maxCentroidMisesPa=float(stress[mask].max()) if mask.any() else None)
    g=request['geometry'];regions={'BODY':region(np.ones(len(cells),bool))}
    regions['SHOULDER']=region(np.linalg.norm(centers,axis=1)<g['hubRadius']+g['blendWidth']+.025) if not request.get('analysisType') else region(np.zeros(len(cells),bool))
    for arm in request['arms']:
        direction=np.array(arm['direction']);axial=centers@direction
        radial=np.linalg.norm(centers-axial[:,None]*direction,axis=1)
        regions['WELD_E'+str(arm['element'])]=region((abs(axial-g['weldDistance'])<=g['weldWidth']/2)&
            (radial>=arm['innerRadius'])&(radial<=arm['outerRadius']+g['reinforcement']))
    cuts=[]
    for cut in raw['cutResultants']:
        expected=np.array(cut['beamExpected']);actual=np.array(cut['wrenchAtCutCenter'])
        changes={}
        for offset,label in ((0,'force'),(3,'moment')):
            scale=np.linalg.norm(expected[offset:offset+3]);delta=np.linalg.norm(actual[offset:offset+3]-expected[offset:offset+3])
            changes[label]={'absoluteDifference':float(delta),'relativeDifference':float(delta/scale) if scale>1 else None}
        original=np.asarray(cut.get('originalBeamExpected',expected))
        original_difference={kind:float(np.linalg.norm(actual[offset:offset+3]-original[offset:offset+3])/max(np.linalg.norm(original[offset:offset+3]),1.)) for offset,kind in ((0,'force'),(3,'moment'))}
        transfer={k:cut[k] for k in ('nodeCount','prescribedTranslation','prescribedRotation','recoveredTranslation','recoveredRotation','maximumDisplacementErrorM') if k in cut}
        cuts.append(dict(element=cut['element'],beamExpected=expected.tolist(),original01Expected=original.tolist(),solidReaction=actual.tolist(),difference=changes,original01RelativeDifference=original_difference,motionTransfer=transfer))
    transmission_passed=all(x['difference'][kind]['relativeDifference']<=.05 if x['difference'][kind]['relativeDifference'] is not None else x['difference'][kind]['absoluteDifference']<=1 for x in cuts for kind in ('force','moment'))
    validation=dict(numericalPassed=raw['relativeResidual']<=1e-9 and raw['forceBalanceRelativeError']<=1e-5 and raw['momentBalanceRelativeError']<=1e-5,
        relativeResidual=raw['relativeResidual'],forceBalanceRelativeError=raw['forceBalanceRelativeError'],momentBalanceRelativeError=raw['momentBalanceRelativeError'],cutDisplacementMaxError=raw['cutDisplacementMaxErrorM'],minimumJacobian=meta['minGmshDetJac'],cadVolumeRelativeError=raw['cadVolumeRelativeError'],
        meshConvergence='not_run',cutLengthSensitivity='not_run',globalLocalTransmission='passed' if transmission_passed else 'differs',
        couplingMode='forceSubmodel',comparisonReference='original 01 section resultants',
        original01Comparison='same_section_resultant_loading',strengthAssessment='not_assessed',cutResultants=cuts)
    validation['boundaryTransferPassed']=bool(raw['cutDisplacementMaxErrorM']<=1e-10)
    submodel=raw.get('submodel')
    if submodel:
        validation['boundaryQuantity']='section_resultants'
        validation['comparisonReference']='original 01 section resultants'
        validation['boundaryMotionPrescribed']=False
        validation['boundaryTransferPassed'] &= transmission_passed
        validation['submodelBoundarySource']=submodel['primarySource']
    validation['numericalPassed'] &= validation['boundaryTransferPassed'] and meta['minGmshDetJac']>0
    validation['globalSolutionAudit']=request.get('globalSolutionAudit')
    if raw.get('memberLoadTransfer'):
        validation['memberLoadTransfer']=raw['memberLoadTransfer']
        validation['numericalPassed'] &= raw['memberLoadTransfer']['passed']
    validation['forceReferenceComparison']='within_5_percent' if transmission_passed else 'differs'
    validation['forceReferenceMeaning']='Conservation of prescribed cut resultants is a boundary construction check, not independent stress accuracy validation.'
    warnings=list(request['warnings'])
    answer=dict(schemaVersion=1,kind='standaloneIntegralHub',solver={'id':'standalone','name':'自编曲边 Tet10','usesAbaqus':False,'quadrature':'14-point'},jobId=job_id,node=request['node'],origin=request['origin'],
        fingerprint=request['fingerprint'],localRequest=request,modelSnapshot=request['modelSnapshot'],sectionAudit=request['sectionAudit'],tubeArms=request['arms'],coordinateFrame={'origin':request['origin'],'axes':'global XYZ','units':'m'},
        mesh={'nodes':np.round(points[boundary],11).tolist(),'tri6':tri6.tolist(),'faces':faces.tolist(),'nodalMisesMPa':np.round(cloud/1e6,6).tolist(),'displacement':np.round(u,13).tolist()},
        result={'nodeCount':len(points),'elementCount':len(cells),'elementType':'曲边 Tet10','meshSize':meta['bodySize'],'focusSize':meta['focusSize'],'toeMeshSize':meta['toeSize'],'cutLength':raw['cutLengthM'],
            'maximumNodalAveragedMisesPa':raw['maximumNodalAveragedMisesPa'],'maximumElementNodalMisesPa':raw['maximumElementNodalMisesPa'],'strainEnergyJ':raw['strainEnergyJ'],'iterations':raw['iterations'],'regions':regions,'timing':raw['timing']},
        validation=validation,coupling=raw.get('coupling'),submodel=submodel,toePaths=toes,shoulderPaths=shoulders,warnings=warnings,
        stressDefinition='显示值：节点体积加权平均应力张量的 Mises。焊趾/肩部峰值：所有相邻单元的未平均单侧应力。全模型峰值另列；不等同于焊趾峰值。')
    (directory/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    if raw.get('memberLoadTransfer'):answer['memberLoadTransfer']=raw['memberLoadTransfer']
    if request.get('analysisType'):
        answer['analysisType']=request['analysisType'];answer['samplingPaths']=toes;answer['toePaths']={};answer['shoulderPaths']={}
        answer['result']['regions']={'BODY':regions['BODY']}
        answer['stressDefinition']='显示值为节点平均Mises；收敛采用固定物理杆段区域的未平均单元侧应力和固定位置取样。无球形节点和焊缝。理想固支边缘峰值另列但不作为实际焊缝应力。'
        if raw.get('submodel',{}).get('support'):answer['validation']['idealSupport']=raw['submodel']['support']
    with (directory/'stress.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['pointIndex','globalX_m','globalY_m','globalZ_m','nodalAverageMises_Pa'])
        for i in boundary:writer.writerow([int(i),*(points[i]+request['origin']),nodal_mises[i]])
    return answer
