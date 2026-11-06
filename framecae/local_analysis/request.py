"""Backend-neutral, immutable beam-to-solid B-node request; SI and global XYZ."""
import hashlib
import numpy as np
from framecae.io.payload import payload_to_model
from framecae.local_analysis.beam_interpolation import interpolate_beam_section
from framecae.postprocess.internal_force import evaluate_section
from framecae.solver.static_solver import StaticSolver
import json

def number(settings,key,default):
    raw=settings.get(key);value=float(default if raw is None or raw=='' else raw)
    if not np.isfinite(value) or value<=0:raise ValueError(f'{key} must be finite and positive')
    return value

def prepare_b_request(request):
    if not isinstance(request, dict) or not isinstance(request.get('settings', {}), dict):
        raise ValueError('请求应包含 model 和 settings 对象。')
    model = payload_to_model(request.get('model'))
    settings = dict(request.get('settings', {}))
    if settings.get('node') in (None, ''):
        raise ValueError('请从当前模型选择需要分析的节点。')
    node = int(settings['node'])
    if node not in model.nodes:
        raise ValueError(f'节点 N{node} 不存在。')
    if any(nid == node for nid, _ in model.prescribed_dofs):
        raise ValueError('本版一体节点件分析支持非支座节点；支座须另外定义实体支承区域。')
    elements = [e for e in model.elements.values() if node in (e.start_node.id, e.end_node.id)]
    max_arms = 8
    if not 1 <= len(elements) <= max_arms:
        raise ValueError(f'通用节点实体分析支持 1 到 {max_arms} 根相连圆管；当前节点连接 {len(elements)} 根。')
    directions, radii, inner = [], [], []
    for e in elements:
        other = e.end_node if e.start_node.id == node else e.start_node
        d = other.coordinates - model.nodes[node].coordinates
        directions.append(d / np.linalg.norm(d))
        r = e.section.characteristic_size / 2
        ri2 = r*r - e.section.area / np.pi
        if r <= 0 or not 0 < ri2 < r*r:
            raise ValueError(f'E{e.id} 必须是由 D、A 定义的空心圆管。')
        radii.append(r)
        inner.append(float(np.sqrt(ri2)))
    # T、Y、K、X 等节点允许任意夹角。只拒绝几乎同向的重复圆管，
    # 因为它们会在局部实体中完全重叠，必须先在 01 中合并。
    for index, first in enumerate(directions):
        for second in directions[index + 1:]:
            if float(np.dot(first, second)) > 0.995:
                raise ValueError('节点存在两根几乎同向的重叠圆管；请先在 01 中合并该方向的连续构件。')
    material = elements[0].material
    if any(not np.allclose([e.material.elastic_modulus, e.material.poisson_ratio, e.material.density],
                           [material.elastic_modulus, material.poisson_ratio, material.density], rtol=1e-10)
           for e in elements):
        raise ValueError('本版要求相连管件采用相同母材弹性参数和密度。')
    r, ri = max(radii), inner[int(np.argmax(radii))]
    smallest_r=min(radii)
    t = r-ri
    blend = number(settings, 'blendWidth', .1875*smallest_r)
    orthogonal_three=len(elements)==3 and all(abs(a@b)<1e-6 for i,a in enumerate(directions) for b in directions[i+1:])
    from framecae.abaqus_local.complex_geometry import clearance
    pairs,required=clearance(directions,radii,blend)
    hub = number(settings, 'hubRadius', max(1.5*r,required))
    if hub<required*(1-1e-8):
        raise ValueError(f'短颈与肩部空间不足；该节点球半径至少需 {required:.6g} m，请识别当前节点并更新几何。')
    seam = number(settings, 'weldDistance', hub+blend+.9125*r)
    width = number(settings, 'weldWidth', .225*smallest_r)
    height = number(settings, 'reinforcement', .025*smallest_r)
    toe = number(settings, 'toeRadius', .05*smallest_r)
    h = number(settings, 'meshSize', .3125*smallest_r)
    hf = number(settings, 'focusSize', .125*smallest_r)
    ht = number(settings, 'toeSize', min(hf,toe))
    cut = number(settings, 'cutLength', max(min(10*r,.45*min(e.length for e in elements)),seam+width/2+max(2*h,r)+.1*r))
    cap = number(settings, 'loadRadius', .6875*smallest_r)
    if not r < hub or not 0 < blend < smallest_r:
        raise ValueError('节点球半径应大于管半径，肩部圆角半径应小于管半径。')
    if seam-width/2 <= hub+blend or cut <= seam+width/2+max(2*h, r):
        raise ValueError('焊缝应在肩部外侧，截断面应在焊缝外至少一个管半径；请增大截断长度。')
    if toe >= (width*width/4+height*height)/(2*height):
        raise ValueError('焊趾半径过大，无法构造给定宽度与余高的相切圆弧焊缝。')
    if cap >= .95*hub or hf > h or hf < 0.0001 or h > r or ht > hf or ht < .0001:
        raise ValueError('加载区域或网格尺寸不合理：加载半径须小于球半径，局部尺寸须不大于外围尺寸。')
    warnings = ['焊接完成后的线弹性理想模型；未考虑缺陷、残余应力、热循环和疲劳。',
                '承载区域、节点件及焊缝尺寸是演示建模假设，请用设计尺寸替换。',
                f'当前节点含 {len(elements)} 根相连圆管；T、Y、K、X 等拓扑共用同一截面内力驱动实体计算流程。',
                '新模型肩部采用实际几何圆角；原 N5 包使用 smooth-min 平滑宽度，两者参数含义不同。',
                '焊缝与母材弹性参数相同，连续实体中的焊缝区域按单元中心所属的轴向范围统计。']
    if ht > toe/2:
        warnings.append('当前局部网格大于焊趾半径的一半，适合流程验证；焊趾局部峰值尚需进一步细化。')
    if model.self_weight_enabled and settings.get('couplingMode')!='forceSubmodel':
        warnings.append('局部实体包含节点件实际体积的自重，01 理想梁杆未必包含相同节点件质量；需核对整体质量理想化。')
    inertias=[np.pi*(ro**4-rin**4)/4 for ro,rin in zip(radii,inner)]
    exact_i=inertias[0]
    section_consistent=all(np.allclose([e.section.iy,e.section.iz,e.section.torsion_constant],
                          [I,I,2*I],rtol=.01,atol=1e-15) for e,I in zip(elements,inertias))
    if not section_consistent and not settings.get('allowInconsistentSection',False):
        raise ValueError('01 的 Iy/Iz/J 与 D、A 对应圆管不一致。请按圆管截面统一参数并重新计算 01；原输入须另存。')
    if not section_consistent:
        warnings.append('诊断模式：截面惯性与实体圆管不一致，不能认定整体—局部验证通过。')
    from .global_solution import read_solution
    global_result, global_audit = read_solution(request, model)
    arms = []
    retained_line_loads = []
    for e, direction, ro, rin in zip(elements, directions, radii, inner):
        if cut >= .48*e.length:
            raise ValueError(f'E{e.id} 截取过长；切口应小于杆长的 0.48 倍。')
        if model.element_temperature_changes.get(e.id, 0) or model.element_length_deviations.get(e.id, 0):
            raise ValueError(f'E{e.id} 含温差或制造初始应变，本版不能静默忽略这些初始状态。')
        uniform_global = np.zeros(3)
        for load in model.member_loads.get(e.id, []):
            if np.any(np.abs(load.local_components) > 1e-12):
                distance = getattr(load, 'position', None)
                if distance is None:
                    uniform_global += e.rotation.T @ load.local_components
                    continue
                distance = distance if e.start_node.id == node else e.length-distance
                if distance <= cut+1e-9:
                    raise ValueError(f'E{e.id} 的杆上集中力落在局部保留区，需要实体加载面。')
        position = cut if e.start_node.id == node else e.length-cut
        state = interpolate_beam_section(model, global_result, e.id, position)
        section = evaluate_section(model, global_result, e.id, position)
        # End-force values use the existing beam section conventions, saved verbatim.
        internal = section.forces.tolist()
        sign = -1 if e.start_node.id == node else 1
        cut_wrench = sign*np.r_[e.rotation.T@section.forces[:3],e.rotation.T@section.forces[3:]]
        arms.append({'element':e.id,'direction':direction.tolist(),'length':cut,
                     'outerRadius':ro,'innerRadius':rin,'center':(cut*direction).tolist(),
                     'translation':state.translation.tolist(),'rotation':state.rotation.tolist(),
                     'beamSection':internal,'beamCutWrench':cut_wrench.tolist(),'beamRotation':e.rotation.tolist(),
                     'nominalStress':float(section.nominal_stress)})
        weight_global = (e.material.density*e.section.area*model.gravity
                         if model.self_weight_enabled and settings.get('couplingMode')=='forceSubmodel' else np.zeros(3))
        if np.any(uniform_global) or np.any(weight_global):
            retained_line_loads.append({'element':e.id,'globalQ':(uniform_global+weight_global).tolist(),
                'uniformGlobalQ':uniform_global.tolist(),'selfWeightGlobalQ':weight_global.tolist(),
                'outwardIntervalM':[0.,cut],
                'originalMemberIntervalM':[0.,cut] if e.start_node.id==node else [e.length-cut,e.length],
                'memberStartsAtSelectedNode':e.start_node.id==node,'unit':'N/m'})
    force = model.nodal_loads.get(node,np.zeros(6)).tolist()
    chosen_direction=settings.get('loadDirection')
    if chosen_direction is None and orthogonal_three:chosen_direction=[0,0,1]
    if chosen_direction is None and np.linalg.norm(force)>1e-12:
        from framecae.abaqus_local.complex_geometry import cap_direction
        chosen_direction=cap_direction([{**a,'geometry':{'blendWidth':blend}} for a in arms],hub,cap)
    direction = np.asarray(chosen_direction if chosen_direction is not None else [0,0,1],dtype=float)
    if direction.shape != (3,) or not np.all(np.isfinite(direction)) or np.linalg.norm(direction) < 1e-9:
        raise ValueError('loadDirection 应为有效的三个方向分量。')
    direction /= np.linalg.norm(direction)
    if np.linalg.norm(force)>1e-12 and any(np.dot(direction,d) > .65 for d in directions):
        raise ValueError('所选承载帽方向与短颈重叠；请更换承载面方向。')
    coupling=settings.get('couplingMode','forceSubmodel')
    if coupling!='forceSubmodel':raise ValueError('本发行版只支持01截面内力驱动；请使用当前03参数。')
    shear_distribution=settings.get('shearDistribution','saintVenantAnnulus')
    if coupling=='forceSubmodel':
        if shear_distribution not in ('resultantAffine','saintVenantAnnulus'):raise ValueError('未知的切口剪力分布。')
        settings['shearDistribution']=shear_distribution
    if retained_line_loads and coupling!='forceSubmodel':
        raise ValueError('保留区域含均布线荷载，请选择“01截面内力驱动子模型”。')
    if coupling=='forceSubmodel':warnings.append('截面内力子模型：01内力转为保持合力与合矩的曲面载荷；01位移仅确定刚体姿态，不强加各切口运动；不自动修正01节点刚度。')
    prepared = {'schemaVersion':2,'node':node,'origin':model.nodes[node].coordinates.tolist(),
                'topology':{'armCount':len(arms),'kind':'two_arm' if len(arms)==2 else 'three_arm' if len(arms)==3 else 'multi_arm'},
                'couplingMode':coupling,'globalSolutionAudit':global_audit,
                'geometryPrecheck':{'passed':True,'minimumAngleDegrees':min((p['angleDegrees'] for p in pairs),default=180.),'requiredHubRadius':required,'legacyOrthogonalThree':orthogonal_three},
                'units':{'length':'m','force':'N','stress':'Pa','rotation':'rad'},
                'geometry':{'hubRadius':hub,'blendWidth':blend,'shoulderRadius':blend,'boreStart':.75*hub,
                            'shoulderConstruction':'analytic tangent circle revolution',
                            'boreFull':.75*hub+ri,'boreShape':'hemisphericalBlindEnd','weldDistance':seam,
                            'weldWidth':width,'reinforcement':height,'toeRadius':toe},
                'mesh':{'size':h,'focusSize':hf,'toeSize':ht,'elementType':'C3D10','meshingRevision':7,'refinementStrategy':'toeBandsV1','algorithm3D':10,'boundaryPlacement':'locally minimized CAD distance to edge chord midpoint','removeConstructionEntities':True},
                'sectionAudit':{'passed':section_consistent,'Iy':exact_i,'Iz':exact_i,'J':2*exact_i,'outerRadius':radii[0],'innerRadius':inner[0],
                    'arms':[{'element':e.id,'outerRadius':ro,'innerRadius':rin,'Iy':I,'Iz':I,'J':2*I} for e,ro,rin,I in zip(elements,radii,inner,inertias)]},
                'material':{'E':material.elastic_modulus,'nu':material.poisson_ratio,'density':material.density},
                'arms':arms,'load':{'wrench':force,'direction':direction.tolist(),'radius':cap,
                                   'source':'01 nodal force/moment; equivalent bearing cap'},
                'gravity':model.gravity.tolist() if model.self_weight_enabled else [0,0,0],
                'warnings':warnings,'modelSnapshot':request['model'],'settingsSnapshot':settings,
                'assumptions':{'weld':'continuous full penetration butt weld; tangent circular toe/crown',
                               'weldMaterial':'same as base metal','updatesParentModel':False}}
    if retained_line_loads:
        prepared['memberLoadMapping']={'revision':1,'loads':retained_line_loads,
            'regionAssignment':'unique nearest radius-normalized arm segment; hub and overlaps partitioned once',
            'projection':'minimum L2 volume density with 12 discrete Euler-Bernoulli virtual-work constraints',
            'selfWeight':'01 ideal beam rho*A*g; no additional solid hub weight' if model.self_weight_enabled else 'disabled',
            'physicalMeaning':'equivalent line loading, not prescribed physical surface pressure'}
        warnings.append('均布线荷载按杆轴0至切口积分；节点件及重叠区按最近归一化杆轴唯一归属，采用保持12个梁自由度虚功的一致体积载荷投影；不等同于实际表面压力。')
        if model.self_weight_enabled:
            warnings.append('截面内力模式的自重沿用01理想梁rho*A*g，不额外叠加实体节点件体积重量；节点件实际质量未另行建模。')
    prepared['fingerprint'] = hashlib.sha256(json.dumps(prepared,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if coupling=='forceSubmodel':
        prepared['shearDistribution']=shear_distribution
        prepared['fingerprint']=hashlib.sha256(json.dumps({k:v for k,v in prepared.items() if k!='fingerprint'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    return prepared


