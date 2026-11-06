"""Straight continuous member and ideal clamp; no hub or fictitious weld."""
import numpy as np
from framecae.io.payload import payload_to_model
from framecae.local_analysis.global_solution import read_solution
from framecae.local_analysis.beam_interpolation import interpolate_beam_section
from framecae.postprocess.internal_force import evaluate_section


def prepare(payload):
    model=payload_to_model(payload['model']);s=dict(payload['settings']);node=int(s['node'])
    if node not in model.nodes:raise ValueError('所选节点不存在')
    es=[e for e in model.elements.values() if node in (e.start_node.id,e.end_node.id)]
    fixed=any(n==node for n,k in model.prescribed_dofs)
    if fixed:
        if len(es)!=1 or set(k for n,k in model.prescribed_dofs if n==node)!=set(range(6)):
            raise ValueError('理想固支首版要求单根圆管、六个自由度全部约束。')
        if any(abs(v)>1e-14 for (n,k),v in model.prescribed_dofs.items() if n==node):
            raise ValueError('理想固支首版仅支持零位移约束')
        kind='idealClamp'
    else:
        if len(es)!=2:raise ValueError('连续直圆管分析要求两段共线管件；此处不是球形焊接接头')
        kind='continuousPipe'
    result,audit=read_solution(payload,model);origin=model.nodes[node].coordinates
    arms=[];line_loads=[];mat=es[0].material;ro0=ri0=None
    L=float(s.get('cutLength',.4));h=float(s.get('meshSize',.015));hf=float(s.get('focusSize',.005));ht=float(s.get('toeSize',.0025))
    if not .0001<=ht<=hf<=h<=.05 or not np.isfinite(L) or L<=.1:raise ValueError('杆段截取长度或网格尺寸无效')
    for e in es:
        d=(e.end_node.coordinates-origin) if e.start_node.id==node else (e.start_node.coordinates-origin);d=d/np.linalg.norm(d)
        ro=e.section.characteristic_size/2;ri2=ro*ro-e.section.area/np.pi
        if not 0<ri2<ro*ro:raise ValueError('要求空心圆管截面')
        ri=np.sqrt(ri2);I=np.pi*(ro**4-ri**4)/4
        if not np.allclose([e.section.iy,e.section.iz,e.section.torsion_constant],[I,I,2*I],rtol=1e-8,atol=1e-15):raise ValueError('圆管截面面积和惯性不一致')
        if ro0 is None:ro0,ri0=ro,ri
        if not np.allclose([ro,ri,mat.elastic_modulus,mat.poisson_ratio],[ro0,ri0,e.material.elastic_modulus,e.material.poisson_ratio],rtol=1e-10):raise ValueError('连续圆管须采用相同材料和截面')
        if L>=.48*e.length:raise ValueError('局部截取长度必须小于杆长0.48倍')
        if model.element_temperature_changes.get(e.id,0) or model.element_length_deviations.get(e.id,0):raise ValueError('暂不支持初始应变')
        q=np.zeros(3)
        for load in model.member_loads.get(e.id,[]):
            p=getattr(load,'position',None)
            if p is None:q+=e.rotation.T@load.local_components
            elif (p if e.start_node.id==node else e.length-p)<=L+1e-9:raise ValueError('杆内集中力请先设置保持物理杆身份的计算分段点，再选连续杆段分析')
        if model.self_weight_enabled:q+=e.material.density*e.section.area*model.gravity
        if np.any(q):line_loads.append(dict(element=e.id,globalQ=q.tolist(),outwardIntervalM=[0.,L],originalMemberIntervalM=[0,L] if e.start_node.id==node else [e.length-L,e.length],memberStartsAtSelectedNode=e.start_node.id==node,unit='N/m'))
        x=L if e.start_node.id==node else e.length-L
        state=interpolate_beam_section(model,result,e.id,x);section=evaluate_section(model,result,e.id,x)
        sign=-1 if e.start_node.id==node else 1
        wrench=sign*np.r_[e.rotation.T@section.forces[:3],e.rotation.T@section.forces[3:]]
        arms.append(dict(element=e.id,direction=d.tolist(),length=L,center=(L*d).tolist(),outerRadius=ro,innerRadius=ri,translation=state.translation.tolist(),rotation=state.rotation.tolist(),beamSection=section.forces.tolist(),beamCutWrench=wrench.tolist(),beamRotation=e.rotation.tolist(),nominalStress=float(section.nominal_stress)))
    if len(arms)==2 and np.dot(arms[0]['direction'],arms[1]['direction'])>-.999999:raise ValueError('该位置不是直圆管，不能用连续杆段替代真实接头')
    force=np.asarray(model.nodal_loads.get(node,np.zeros(6)))
    if fixed and np.linalg.norm(force)>1e-12:raise ValueError('支座节点直接载荷须明确实际施加面，本次不自动投影到固定面')
    d=np.asarray(arms[0]['direction']);f=force[:3];normal=-f+d*(d@f)
    if np.linalg.norm(normal)<1e-10:
        normal=np.eye(3)[np.argmin(abs(d))];normal-=d*(d@normal)
    normal/=np.linalg.norm(normal)
    width=float(s.get('patchWidth',.02));angle=float(s.get('patchAngleDegrees',60))
    if not 0<width<min(.15,2*L) or not 5<=angle<=180:raise ValueError('加载面片宽度或周向范围无效')
    s.update(analysisType=kind,node=node,couplingMode='forceSubmodel',solverMethod='standalone')
    q=dict(schemaVersion=2,node=node,analysisType=kind,origin=origin.tolist(),topology=dict(armCount=len(arms),kind=kind),
           couplingMode='forceSubmodel',shearDistribution=s.get('shearDistribution','saintVenantAnnulus'),globalSolutionAudit=audit,
           geometry=dict(kind=kind,hubRadius=0.,blendWidth=0.,weldDistance=0.,weldWidth=0.,reinforcement=0.,toeRadius=0.,axis=d.tolist(),patchWidth=width,patchAngleDegrees=angle,patchNormal=normal.tolist()),
           mesh=dict(size=h,focusSize=hf,toeSize=ht,elementType='C3D10',meshingRevision=3,algorithm3D=10,boundaryPlacement='locally minimized CAD distance to edge chord midpoint'),
           sectionAudit=dict(passed=True,Iy=I,Iz=I,J=2*I,outerRadius=ro0,innerRadius=ri0),
           geometryPrecheck=dict(passed=True),material=dict(E=mat.elastic_modulus,nu=mat.poisson_ratio,density=mat.density),arms=arms,
           load=dict(wrench=force.tolist(),direction=normal.tolist(),radius=width,source='01 nodal force; smooth finite pipe surface patch'),
           gravity=[0,0,0],warnings=['连续圆管不建立球形节点或焊缝。',f'加载面片宽度{width*1000:g}mm、周向{angle:g}度为新增示范假设；固定尺寸后检验网格收敛。' if not fixed else '理想端面全固定；固支边缘的奇异峰值不作为实际支座焊缝应力。'],
           modelSnapshot=payload['model'],settingsSnapshot=s,units=dict(length='m',force='N',stress='Pa',rotation='rad'),
           assumptions=dict(updatesParentModel=False,weld='none',support='ideal clamped annular face' if fixed else 'none'))
    if fixed:q['supportExpected']=result.reactions[model.nodes[node].dof_indices].tolist()
    if line_loads:q['memberLoadMapping']=dict(revision=1,loads=line_loads,projection='12 beam virtual-work constraints',selfWeight='included in line loads')
    return q
