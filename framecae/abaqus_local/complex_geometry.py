"""Admissible 3--8-arm integral hubs, preserving the original three-arm path."""
import copy
import hashlib
import json
import math
import numpy as np

from framecae.io.payload import payload_to_model
from framecae.local_analysis.beam_interpolation import interpolate_beam_section
from framecae.postprocess.internal_force import evaluate_section
from framecae.solver.static_solver import StaticSolver


class JointGeometryError(ValueError):
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def positive(row, key, default):
    value = row.get(key)
    value = float(default if value in (None, '') else value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError('%s 必须为有限正数。' % key)
    return value


def clearance(directions, radius, blend):
    radii=np.broadcast_to(np.asarray(radius,dtype=float),(len(directions),))
    pairs=[]
    for i,a in enumerate(directions):
        for j in range(i+1,len(directions)):
            angle=float(np.arccos(np.clip(a@directions[j],-1.,1.)))
            if angle < 1e-5:
                raise ValueError('存在同向重叠杆件；相反方向的共线杆件允许。')
            # Neck outer circles + shoulder clearance must be separated outside the core.
            r=max(radii[i],radii[j])
            required=math.sqrt(((r+blend)/math.sin(angle/2))**2+r**2)*1.05
            pairs.append({'first':i,'second':j,'angleDegrees':math.degrees(angle),'requiredHubRadius':required})
    return pairs,max((p['requiredHubRadius'] for p in pairs),default=1.5*max(radii))


def cap_direction(arms, hub, cap, explicit=None):
    def margin(v):
        cap_angle=math.asin(min(cap/hub,.9999))
        return min(math.acos(float(np.clip(v@a['direction'],-1,1)))-cap_angle-
                   math.asin(min((a['outerRadius']+a['geometry']['blendWidth'])/hub,.9999)) for a in arms)
    if explicit is not None:
        v=np.asarray(explicit,dtype=float)
        if v.shape!=(3,) or not np.isfinite(v).all() or np.linalg.norm(v)<1e-9:
            raise ValueError('loadDirection 必须为有效三分量方向。')
        v=v/np.linalg.norm(v)
        if margin(v)<.02:raise ValueError('承载面与短颈相交，请调整实际加载面方向或半径。')
        return v.tolist()
    candidates=[*np.eye(3),*-np.eye(3)]
    for k in range(120):
        z=1-2*(k+.5)/120;t=k*np.pi*(3-np.sqrt(5));r=np.sqrt(1-z*z)
        candidates.append(np.array([r*np.cos(t),r*np.sin(t),z]))
    v=max(candidates,key=margin)
    if margin(v)<.02:raise ValueError('没有可用的球面承载区域，需要定义实际承载构造。')
    return v.tolist()


def prepare_complex(request):
    if not isinstance(request,dict) or not isinstance(request.get('settings',{}),dict):
        raise ValueError('请求应包含 model 和 settings 对象。')
    settings=request.get('settings',{});model=payload_to_model(request.get('model'))
    node=int(settings.get('node',5))
    if node not in model.nodes:raise ValueError('节点不存在。')
    if any(nid==node for nid,_ in model.prescribed_dofs):raise ValueError('当前仅支持非支座节点。')
    elements=[e for e in model.elements.values() if node in (e.start_node.id,e.end_node.id)]
    if not 3<=len(elements)<=8:raise ValueError('当前复杂节点支持3–8个相连圆管杆端。')
    radii=[];inners=[];directions=[]
    for e in elements:
        r=e.section.characteristic_size/2;ri2=r*r-e.section.area/np.pi
        if r<=0 or not 0<ri2<r*r:raise ValueError('E%d 不是有效的空心圆管截面。'%e.id)
        radii.append(r);inners.append(np.sqrt(ri2))
        neighbor=e.end_node if e.start_node.id==node else e.start_node
        d=neighbor.coordinates-model.nodes[node].coordinates;directions.append(d/np.linalg.norm(d))
    if not np.allclose(radii,radii[0],rtol=1e-8) or not np.allclose(inners,inners[0],rtol=1e-8):
        raise ValueError('本版复杂节点要求等径、等壁厚圆管。')
    material=elements[0].material
    if any(e.material!=material for e in elements):raise ValueError('本版复杂节点要求同一材料。')
    r=float(radii[0]);ri=float(inners[0]);t=r-ri;inertia=np.pi*(r**4-ri**4)/4
    consistent=all(np.allclose([e.section.iy,e.section.iz,e.section.torsion_constant],
                              [inertia,inertia,2*inertia],rtol=.01,atol=1e-15) for e in elements)
    if not consistent:raise ValueError('01截面A、D、Iy、Iz、J与实体圆管不一致，请先统一并重新求解01。')
    blend=positive(settings,'blendWidth',.1875*r)
    pairs,required=clearance(directions,r,blend)
    for pair in pairs:
        pair['elements']=[elements[pair['first']].id,elements[pair['second']].id]
    hub=positive(settings,'hubRadius',max(1.5*r,required))
    width=positive(settings,'weldWidth',.225*r)
    height=positive(settings,'reinforcement',.025*r)
    toe=positive(settings,'toeRadius',.05*r)
    h=positive(settings,'meshSize',.20*r);hf=positive(settings,'focusSize',.10*r)
    ht=positive(settings,'toeSize',.06*r)
    if not 0<blend<r or not ht<=hf<=h<=r:raise ValueError('圆角和网格参数不合理，要求焊趾网格≤局部网格≤外围网格≤管半径。')
    if toe >= (width*width/4+height*height)/(2*height):raise ValueError('焊趾半径与焊缝宽度/余高不相容。')
    seam=positive(settings,'weldDistance',hub+blend+.8*r+width/2)
    minimum_cut=seam+width/2+max(2*h,r)+.1*r
    cut=positive(settings,'cutLength',max(6*r,minimum_cut))
    overrides=settings.get('arms',[])
    if not isinstance(overrides,list):raise ValueError('逐杆参数arms必须为列表。')
    override_map={int(v['element']):v for v in overrides}
    if len(override_map)!=len(overrides) or set(override_map)-{e.id for e in elements}:raise ValueError('逐杆参数含重复或不相连的杆号。')
    diagnostics={'passed':False,'armCount':len(elements),'minimumAngleDegrees':min(p['angleDegrees'] for p in pairs),
                 'requiredHubRadius':required,'hubRadius':hub,'pairs':pairs,
                 'maximumCommonCut':min(.48*e.length for e in elements)}
    if hub < required*(1-1e-8):
        raise JointGeometryError('短颈/肩部空间不足：最小夹角%.3f°，建议球半径至少%.4f m。'%
                                 (diagnostics['minimumAngleDegrees'],required),diagnostics)
    g={'hubRadius':hub,'blendWidth':blend,'shoulderRadius':blend,'boreStart':.75*hub,
       'boreFull':.75*hub+ri,'boreShape':'hemisphericalBlindEnd','weldDistance':seam,
       'weldWidth':width,'reinforcement':height,'toeRadius':toe}
    geometries=[]
    for e in elements:
        override=override_map.get(e.id,{})
        local=copy.deepcopy(g)
        for key in ['blendWidth','shoulderRadius','weldDistance','weldWidth','reinforcement','toeRadius']:
            if key in override:local[key]=positive(override,key,local[key])
        if not np.isclose(local['blendWidth'],blend) or not np.isclose(local['shoulderRadius'],blend):
            raise ValueError('当前各短颈采用同一肩部圆角半径；逐杆可调整焊缝和截断参数。')
        length=positive(override,'cutLength',cut)
        if length>=.48*e.length:
            diagnostics.update(failedElement=e.id,requestedCut=length,maximumCut=.48*e.length)
            raise JointGeometryError('E%d截断空间不足：图B几何需要切口约%.4f m，但该杆允许小于%.4f m；不能穿过邻接节点或缩小球体掩盖短颈碰撞。'%
                                     (e.id,length,.48*e.length),diagnostics)
        if local['weldDistance']-local['weldWidth']/2 <= hub+local['blendWidth'] or length <= local['weldDistance']+local['weldWidth']/2+max(2*h,r):
            raise ValueError('E%d的焊缝或截断面位置过近。'%e.id)
        if local['toeRadius'] >= (local['weldWidth']**2/4+local['reinforcement']**2)/(2*local['reinforcement']):
            raise ValueError('E%d焊趾圆弧参数不相容。'%e.id)
        geometries.append((local,length))
    global_result=StaticSolver(method='scipy').solve(model);arms=[]
    for e,direction,(local,length) in zip(elements,directions,geometries):
        if model.element_temperature_changes.get(e.id,0) or model.element_length_deviations.get(e.id,0):
            raise ValueError('E%d含尚未映射的温差/制造初始应变。'%e.id)
        for load in model.member_loads.get(e.id,[]):
            if not np.any(np.abs(load.local_components)>1e-12):continue
            distance=getattr(load,'position',None)
            if distance is None:raise ValueError('E%d的杆上分布载荷需要定义实体加载区域。'%e.id)
            distance=distance if e.start_node.id==node else e.length-distance
            if distance<=length+1e-9:raise ValueError('E%d的杆上集中力落在局部保留区。'%e.id)
        position=length if e.start_node.id==node else e.length-length
        state=interpolate_beam_section(model,global_result,e.id,position)
        section=evaluate_section(model,global_result,e.id,position)
        sign=-1 if e.start_node.id==node else 1
        wrench=sign*np.r_[e.rotation.T@section.forces[:3],e.rotation.T@section.forces[3:]]
        arms.append({'element':e.id,'direction':direction.tolist(),'length':length,'outerRadius':r,'innerRadius':ri,
                     'geometry':local,'center':(length*direction).tolist(),'translation':state.translation.tolist(),
                     'rotation':state.rotation.tolist(),'beamSection':section.forces.tolist(),
                     'beamCutWrench':wrench.tolist(),'beamRotation':e.rotation.tolist(),
                     'nominalStress':float(abs(section.nominal_stress))})
    force=model.nodal_loads.get(node,np.zeros(6)).tolist()
    cap=positive(settings,'loadRadius',.6*r)
    if cap>=.95*hub:raise ValueError('承载区域半径过大。')
    loaded=bool(np.linalg.norm(force)>1e-12)
    direction=cap_direction(arms,hub,cap,settings.get('loadDirection')) if loaded else [0.,0.,1.]
    diagnostics['passed']=True
    warnings=['单档网格及固定截断参数的初步验证，未验证网格收敛或截断距离敏感性。',
              '图B采用各杆端独立短颈与环焊缝；共线两侧不自动视为贯通主管。',
              '焊缝与母材采用相同弹性参数、连续全熔透理想实体；未考虑缺陷、热循环、残余应力及疲劳。',
              '01按理想刚接梁计算；局部实体柔度不反馈整体模型。']
    if loaded:warnings.append('承载区域是可修改的物理假设，节点六分量外载经分布式耦合传递。')
    if model.self_weight_enabled:warnings.append('局部节点件的实际质量与整体梁理想化质量需要另行核对。')
    q={'schemaVersion':2,'node':node,'origin':model.nodes[node].coordinates.tolist(),
       'units':{'length':'m','force':'N','stress':'Pa','rotation':'rad'},'geometry':g,
       'mesh':{'size':h,'focusSize':hf,'toeSize':ht,'elementType':'C3D10','meshingRevision':3},
       'sectionAudit':{'passed':consistent,'Iy':inertia,'Iz':inertia,'J':2*inertia,'outerRadius':r,'innerRadius':ri},
       'geometryPrecheck':diagnostics,'material':{'E':material.elastic_modulus,'nu':material.poisson_ratio,'density':material.density},
       'arms':arms,'load':{'wrench':force,'direction':direction,'radius':cap,'active':loaded,
                        'source':'01 nodal force/moment; physical bearing patch','transfer':'continuumDistributingCoupling'},
       'gravity':model.gravity.tolist() if model.self_weight_enabled else [0,0,0],
       'warnings':warnings,'modelSnapshot':request['model'],'settingsSnapshot':settings,
       'assumptions':{'weld':'continuous full penetration butt weld; tangent circular toe/crown',
                      'weldMaterial':'same as base metal','oneWayGlobalLocal':True,'validationScope':'single_mesh_single_cut'}}
    q['fingerprint']=hashlib.sha256(json.dumps(q,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return q
