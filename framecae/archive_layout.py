"""Relocatable four-folder layout, case routing, and completed-result access."""
from pathlib import Path
import json, os, re, copy

# In the integrated distribution the application and its four project folders
# share one root (unlike the archival source, where code lived in 01_网页程序).
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'02_模型输入'
RESULTS=Path(os.environ.get('FRAMECAE_SOLID_RUNS',str(ROOT/'04_网页计算结果')))
PATTERN=re.compile(r'[0-9a-f]{32}')

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def model_key(model):
    from framecae.io.payload import payload_to_model,model_to_payload
    return json.dumps(model_to_payload(payload_to_model(model)),sort_keys=True,allow_nan=False)

def case_id(model):
    wanted=model_key(model)
    for item in load_json(INPUT/'算例目录.json')['cases']:
        if model_key(load_json(INPUT/item['id']/item['modelFile']))==wanted:
            return item['id']
    return '99_自定义模型'

def job_id(folder):
    """Read the stable internal ID independently of the display folder name."""
    try:
        value=load_json(Path(folder)/'status.json').get('jobId')
    except (OSError,ValueError,AttributeError):return None
    return value if isinstance(value,str) and PATTERN.fullmatch(value) else None

def jobs(root=None):
    root=Path(root or RESULTS)
    if not root.exists():return
    for folder in root.iterdir():
        if not folder.is_dir():continue
        if job_id(folder):yield folder
        else:
            for p in folder.iterdir():
                if p.is_dir() and job_id(p):yield p

def find_job(job,root=None):
    if not PATTERN.fullmatch(str(job)):raise ValueError('无效作业编号。')
    root=Path(root or RESULTS)
    direct=root/job
    if direct.is_dir() and job_id(direct)==job:return direct
    matches=[p for p in jobs(root) if job_id(p)==job]
    if len(matches)!=1:raise ValueError('未找到唯一的保存作业。')
    return matches[0]

def new_job(root,job,q):
    folder=Path(root)/case_id(q['modelSnapshot'])/job
    folder.mkdir(parents=True)
    return folder

def settings_from_request(q):
    return {**q.get('settingsSnapshot',{}),**q['geometry'],'node':q['node'],
            'couplingMode':q['couplingMode'],'shearDistribution':q['shearDistribution'],
            'cutLength':q['arms'][0]['length'],'meshSize':q['mesh']['size'],
            'focusSize':q['mesh']['focusSize'],'toeSize':q['mesh']['toeSize'],
            'loadRadius':q['load']['radius'],'loadDirection':q['load']['direction']}

def archived_request(payload):
    """Explicit access to an immutable saved problem; never relabel new geometry."""
    job=payload.get('archiveJobId')
    if not PATTERN.fullmatch(str(job or '')):return None
    try:
        folder=find_job(job)
        if load_json(folder/'status.json').get('state')!='completed':return None
        q=load_json(folder/'local_request.json')
    except (OSError,ValueError):return None
    if model_key(payload['model'])!=model_key(q['modelSnapshot']):return None
    reference=settings_from_request(q);settings=payload.get('settings',{})
    keys=['node','couplingMode','shearDistribution','analysisType','hubRadius','blendWidth',
          'weldDistance','weldWidth','reinforcement','toeRadius','cutLength',
          'meshSize','focusSize','toeSize','loadRadius','loadDirection','patchWidth','patchAngleDegrees']
    def equal(a,b):
        if isinstance(a,(float,int)) and isinstance(b,(float,int)):return abs(a-b)<=1e-12+1e-11*max(abs(a),abs(b))
        if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
        return a==b
    for k in keys:
        if k=='analysisType' and settings.get(k) in (None,'auto') and reference.get(k) in (None,'auto'):continue
        if k in reference and k in settings and not equal(settings[k],reference[k]):return None
    # The supplied 01 must itself be a valid solution of the same current model.
    from framecae.io.payload import payload_to_model
    from framecae.local_analysis.global_solution import read_solution
    read_solution(payload,payload_to_model(payload['model']))
    return q

def catalog():
    answer=copy.deepcopy(load_json(INPUT/'算例目录.json'))
    for c in answer['cases']:
        c['model']=load_json(INPUT/c['id']/c['modelFile'])
        known={t.get('jobId') for t in c['tasks']}
        for p in sorted((RESULTS/c['id']).glob('*/status.json'),key=lambda x:x.stat().st_mtime):
            identity=job_id(p.parent)
            if not identity or identity in known:continue
            s=load_json(p)
            if s.get('state')!='completed' or not (p.parent/'local_results.json').exists():continue
            q=load_json(p.parent/'local_request.json')
            if case_id(q['modelSnapshot'])!=c['id']:continue
            c['tasks'].append(dict(label=f'N{q["node"]} / {q.get("analysisType","B节点")} / h={q["mesh"]["toeSize"]*1000:g}mm',jobId=identity,settings=settings_from_request(q)))
    return answer

def save_results(payload):
    from framecae.solid_local.service import atomic_json
    model=payload['model'];solved=payload['globalResult']
    if model_key(model)!=model_key(solved['solvedModel']):raise ValueError('当前结果与模型不一致，请重新计算01。')
    folder=RESULTS/case_id(model);folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'01_整体计算.json',solved)
    # Save only checks that were actually run for this exact browser model.
    for kind,filename in [('strength','02_强度校核.json'),('stability','04_稳定校核.json')]:
        check=payload.get('checks',{}).get(kind)
        if check is not None:atomic_json(folder/filename,check)
    if folder.name=='99_自定义模型':atomic_json(folder/'模型.json',model)
    return dict(saved=True,folder=str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder))
