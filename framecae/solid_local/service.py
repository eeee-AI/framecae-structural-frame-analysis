"""Immutable requests and isolated jobs for the self-coded solver. No Abaqus required."""
from pathlib import Path
import copy,hashlib,importlib.util,json,os,re,subprocess,sys,threading,uuid,time
from datetime import datetime,timezone
from framecae.local_analysis.request import prepare_b_request

PROJECT=Path(__file__).resolve().parents[2]
from framecae import archive_layout
RUN_ROOT=archive_layout.RESULTS
VERSION='curved-tet10-1.3-submodel'
_lock=threading.RLock()

def atomic_json(path,value):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    for attempt in range(20):
        try:temp.replace(path);break
        except PermissionError:
            if attempt==19:raise
            time.sleep(.025)

def environment():
    modules=['numpy','scipy','gmsh','skfem','pyamg','meshio']
    missing=[name for name in modules if importlib.util.find_spec(name) is None]
    return dict(available=not missing,missing=missing,solver=VERSION,requiresAbaqus=False,supported='B接头：1–8根同材料圆管；新增等截面连续直管有限面片加载、单根圆管理想全固支端。01截面内力、均布线荷载、圣维南圆环剪力分布；线弹性。')

def prepare(payload):
    if not isinstance(payload,dict):raise ValueError('请求应包含 model 和 settings。')
    archived=archive_layout.archived_request(payload)
    if archived is not None:return archived
    req=copy.deepcopy(payload);settings=req.setdefault('settings',{})
    if not isinstance(settings,dict):raise ValueError('settings 必须是对象。')
    if settings.get('connectionType','integralHubRingButtWeld')!='integralHubRingButtWeld':raise ValueError('自编曲边 Tet10 首版仅支持 B 一体节点件。')
    # Geometric defaults are derived from the imported section/directions below.
    # A missing node is selected from this model, never from an example's ID.
    if settings.get('node') in (None,''):
        return suggest(req)
    defaults={}
    for key,value in defaults.items():
        if settings.get(key) in (None,''):settings[key]=value
    settings.setdefault('couplingMode','forceSubmodel')
    if settings['couplingMode']!='forceSubmodel':raise ValueError('本发行版只支持01截面内力驱动。')
    settings['solverMethod']='standalone'
    if settings.get('analysisType') in ('idealClamp','continuousPipe'):
        from .line_request import prepare as prepare_line
        q=prepare_line(req)
    else:
        # A computational split of one continuous pipe must never create a hub.
        from framecae.io.payload import payload_to_model
        import numpy as np
        m=payload_to_model(req['model']);n=int(settings['node'])
        es=[e for e in m.elements.values() if n in (e.start_node.id,e.end_node.id)]
        ds=[(e.end_node.coordinates-e.start_node.coordinates)*(1 if e.start_node.id==n else -1)/e.length for e in es]
        if len(ds)==2 and ds[0]@ds[1]<-.999999:
            from .line_request import prepare as prepare_line
            q=prepare_line(req)
        elif any(nid==n for nid,_ in m.prescribed_dofs):
            from .line_request import prepare as prepare_line
            q=prepare_line(req)
        else:q=prepare_b_request(req)
    if not q['sectionAudit']['passed']:raise ValueError('圆管截面不一致，请先显式统一截面并重算 01。')
    q['solver']={'id':'standalone','version':VERSION,'element':'curved isoparametric Tet10','quadrature':'14-point degree 5'}
    q['fingerprint']=hashlib.sha256(json.dumps({k:v for k,v in q.items() if k!='fingerprint'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    q['warnings']+=[
        '独立曲边 Tet10 计算；Abaqus 仅为可选对照/显示工具。',
        '01→03为截面内力子模型，位移只用于刚体姿态。'+'网格和截断距离分别核对；求解完成不代表这些检查均通过。']
    # Warnings are part of the saved input; hash after finalizing all fields.
    q['fingerprint']=hashlib.sha256(json.dumps({k:v for k,v in q.items() if k!='fingerprint'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    return q


def physical_key(q):
    """Cache the complete physical problem, independent of UI/cosmetic fields."""
    from framecae.io.payload import payload_to_model,model_to_payload
    physical={k:q.get(k) for k in ('node','origin','geometry','arms','mesh','material','load','gravity','solver')}
    if q.get('analysisType'):physical['analysisType']=q['analysisType'];physical['supportExpected']=q.get('supportExpected')
    physical['couplingMode']=q.get('couplingMode','forceSubmodel')
    if q.get('memberLoadMapping'):physical['memberLoadMapping']=q['memberLoadMapping']
    # Legacy jobs without this field used the affine resultant distribution.
    # Keep their physical key intact; the new law has an independent revision.
    if q.get('couplingMode')=='forceSubmodel' and q.get('shearDistribution','resultantAffine')!='resultantAffine':
        physical['shearDistribution']=q['shearDistribution']
        physical['shearDistributionRevision']=1
    physical['modelSnapshot']=model_to_payload(payload_to_model(q['modelSnapshot']))
    def canonical(v):
        if isinstance(v,float):return float(format(v,'.13g'))
        if isinstance(v,list):return [canonical(x) for x in v]
        if isinstance(v,dict):return {k:canonical(value) for k,value in v.items()}
        return v
    return hashlib.sha256(json.dumps(canonical(physical),sort_keys=True,allow_nan=False).encode()).hexdigest()

def job_directory(job):
    if not re.fullmatch('[0-9a-f]{32}',str(job)):raise ValueError('无效作业编号。')
    p=archive_layout.find_job(job,RUN_ROOT)
    if not p.is_dir():raise ValueError('未找到作业。')
    return p


def suggest(payload):
    from framecae.io.payload import payload_to_model
    from framecae.solver.static_solver import StaticSolver
    from framecae.local_analysis.critical_node import rank_critical_nodes
    model=payload_to_model(payload.get('model'))
    from framecae.local_analysis.global_solution import read_solution
    solved,_=read_solution(payload,model)
    nodes=[int(payload['node'])] if payload.get('node') else [r.node_id for r in rank_critical_nodes(model,solved)]
    errors=[]
    for node in nodes:
        try:
            settings={**payload.get('settings',{}),'node':node,'couplingMode':payload.get('couplingMode','forceSubmodel'),
                      'shearDistribution':payload.get('shearDistribution',payload.get('settings',{}).get('shearDistribution','saintVenantAnnulus'))}
            return prepare({'model':payload['model'],'settings':settings,**({'globalSolution':payload['globalSolution']} if payload.get('globalSolution') else {})})
        except ValueError as e:errors.append(str(e))
    raise ValueError('没有通过空间检查的非支座节点：'+'；'.join(dict.fromkeys(errors))[:1200])

def status(job):
    p=job_directory(job);r=json.loads((p/'status.json').read_text('utf-8'))
    r['hasResult']=r['state']=='completed' and (p/'local_results.json').is_file()
    r['files']=[n for n in FILES if (p/n).is_file()]
    return r

def result(job):
    s=status(job)
    if not s['hasResult']:raise ValueError('作业尚未完成。')
    return json.loads((job_directory(job)/'local_results.json').read_text('utf-8'))

FILES={'member_load_transfer.json','source_01.json','local_request.json','local_results.json','submodel.json','validation.json','mesh_meta.json','worker.log','mesh.msh','geometry.step','solution.npz','mesh.npz','model.inp','result.vtu','stress.csv','toe_results.json','shoulder_results.json','toe_samples.npz','study.json','joint_mesh_study.json','export_odb.py'}
FILES.add('cut_stress_flux.json')
def artifact(job,name):
    if name not in FILES:raise ValueError('不允许读取该文件。')
    p=job_directory(job)/name
    if not p.is_file():raise ValueError('该文件尚未生成。')
    return p

def start(payload):
    q=prepare(payload)
    if payload.get('archiveJobId') and q.get('geometry',{}).get('shoulderConstruction') is None and not q.get('analysisType'):
        if payload.get('study'):
            raise ValueError('早期几何归档可恢复或用原网格重算；新的网格研究请先识别当前节点，以新版几何另算并保留原结果。')
        source=archive_layout.find_job(payload['archiveJobId'],RUN_ROOT)
        if not (source/'mesh.npz').is_file():
            raise ValueError('早期几何的原网格缺失，不能用新版几何静默替换。请恢复完整作业文件，或重新识别节点另算。')
    envcheck=environment()
    if not envcheck['available']:raise ValueError('缺少独立求解依赖：'+', '.join(envcheck['missing']))
    study=payload.get('study')
    if study is not None:
        if not isinstance(study,dict):raise ValueError('study 必须是对象。')
        sizes=[float(v) for v in study.get('toeSizes',[])]
        if not 2<=len(sizes)<=4 or any(not .0005<=v<=.004 for v in sizes) or any(a<=b for a,b in zip(sizes,sizes[1:])):raise ValueError('网格研究需 2–4 档递减尺寸，范围 0.5–4 mm。')
        study={'toeSizes':sizes}
    physical=physical_key(q)
    key=hashlib.sha256(json.dumps([physical,study],sort_keys=True).encode()).hexdigest()
    with _lock:
        RUN_ROOT.mkdir(parents=True,exist_ok=True)
        if not payload.get('force',False):
            for p in archive_layout.jobs(RUN_ROOT):
                if not p.is_dir() or not (p/'status.json').is_file():continue
                try:s=json.loads((p/'status.json').read_text('utf-8'))
                except (OSError,ValueError):continue
                if s.get('state') not in ('failed','cancelled') and s.get('cacheKey')!=key and (p/'local_request.json').exists():
                    try:
                        old_study=json.loads((p/'study_request.json').read_text('utf-8')) if (p/'study_request.json').exists() else None
                        if old_study==study and physical_key(json.loads((p/'local_request.json').read_text('utf-8')))==physical:s['cacheKey']=key
                    except (OSError,ValueError,KeyError,TypeError):pass
                if s.get('cacheKey')==key and s.get('state') not in ('failed','cancelled'):
                    if s['state']=='completed':
                        validation=s.get('validation')
                        if validation is None and (p/'local_results.json').exists():
                            validation=json.loads((p/'local_results.json').read_text('utf-8')).get('validation',{})
                        if validation and not validation.get('numericalPassed',False):continue
                    identity=archive_layout.job_id(p)
                    return {'jobId':identity,'cached':s['state']=='completed','reused':True,**status(identity)}
        job=uuid.uuid4().hex;p=archive_layout.new_job(RUN_ROOT,job,q)
        atomic_json(p/'local_request.json',q)
        if payload.get('globalSolution'):atomic_json(p/'source_01.json',payload['globalSolution'])
        if study:atomic_json(p/'study_request.json',study)
        meta=dict(jobId=job,state='queued',message='已排队，等待独立有限元求解。',fingerprint=q['fingerprint'],cacheKey=key,solver=VERSION,createdAt=datetime.now(timezone.utc).isoformat())
        atomic_json(p/'status.json',meta)
        env=dict(os.environ);env['PYTHONIOENCODING']='utf-8'
        for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):env[name]='1'
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with (p/'worker.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,'-u','-m','framecae.solid_local.worker',str(p)],cwd=PROJECT,env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=flags)
        # Worker owns subsequent state writes. Its PID also allows a queued job to cancel.
        atomic_json(p/'process.json',{'pid':process.pid})
        return {'jobId':job,'cached':False,**meta}

def cancel(job):
    p=job_directory(job);s=status(job)
    if s['state'] in ('completed','failed','cancelled'):return s
    (p/'cancel.request').write_text('cancel',encoding='ascii')
    pid=json.loads((p/'process.json').read_text()).get('pid')
    if pid:
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(int(pid)),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            try:os.kill(int(pid),signal.SIGTERM)
            except ProcessLookupError:pass
    s.update(state='cancelled',message='计算已取消。',hasResult=False);atomic_json(p/'status.json',s)
    return s
