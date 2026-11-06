"""Prepare immutable global-to-local requests and manage isolated Abaqus jobs."""
from __future__ import annotations

import hashlib
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import numpy as np

from framecae.io.payload import payload_to_model
from framecae.local_analysis.beam_interpolation import interpolate_beam_section
from framecae.postprocess.internal_force import evaluate_section
from framecae.solver.static_solver import StaticSolver

PROJECT = Path(__file__).resolve().parents[2]
from framecae.abaqus_launcher import find_launcher
LAUNCHER = find_launcher()
RUN_ROOT = Path(os.environ.get('FRAMECAE_ABAQUS_RUNS',str(PROJECT/'03_Abaqus结果'/'自定义局部对照')))


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def number(settings, key, default):
    raw = settings.get(key)
    value = float(default if raw is None or raw == '' else raw)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f'{key} 必须是有限正数。')
    return value


def _prepare_legacy(request):
    from framecae.local_analysis.request import prepare_b_request
    return prepare_b_request(request)


def prepare(request):
    """Keep the verified orthogonal N5 path, dispatch other admissible nodes to v2."""
    if not isinstance(request,dict) or not isinstance(request.get('settings',{}),dict):
        raise ValueError('请求应包含 model 和 settings 对象。')
    settings=request.get('settings',{})
    if int(settings.get('geometryVersion',0))==2:
        from .complex_geometry import prepare_complex
        return prepare_complex(request)
    model=payload_to_model(request.get('model'));node=int(settings.get('node',5))
    elements=[e for e in model.elements.values() if node in (e.start_node.id,e.end_node.id)]
    ds=[]
    for e in elements:
        other=e.end_node if e.start_node.id==node else e.start_node
        d=other.coordinates-model.nodes[node].coordinates;ds.append(d/np.linalg.norm(d))
    if len(ds)==3 and all(abs(a@b)<1e-6 for i,a in enumerate(ds) for b in ds[i+1:]):
        return _prepare_legacy(request)
    from .complex_geometry import prepare_complex
    return prepare_complex(request)


def circular_sections(request):
    """Explicit correction of the circular sections connected to the B node."""
    original=request.get('model');model=payload_to_model(original)
    node=int(request.get('node',5))
    sections={e.section.id:e.section for e in model.elements.values() if node in (e.start_node.id,e.end_node.id)}
    if not sections:raise ValueError('所选节点没有相连截面。')
    corrected=copy.deepcopy(original);changes=[]
    for row in corrected['sections']:
        section=sections.get(int(row['id']))
        if section is None:continue
        radius=section.characteristic_size/2
        inner_squared=radius**2-section.area/np.pi
        if not 0<inner_squared<radius**2:raise ValueError('D、A 无法组成空心圆管。')
        inertia=np.pi*(radius**4-inner_squared**2)/4
        target={'iy':float(inertia),'iz':float(inertia),'j':float(2*inertia)}
        changes.append({'section':section.id,'before':{k:row.get(k) for k in target},'after':target})
        row.update(target)
    return {'model':corrected,'changes':changes,'node':node,'definition':'circular hollow section from D and A'}


def verified_result(job):
    answer=json.loads(artifact(job,'local_results.json').read_text('utf-8'))
    summary=PROJECT/'verification'/'weld_toe'/'summary.json'
    if summary.is_file():
        report=json.loads(summary.read_text('utf-8'))
        if job in report.get('coveredJobIds',[]):
            samples=artifact(job,'toe_samples.json')
            records=json.loads(samples.read_text('utf-8'))['records']
            for key,value in report['toes'].items():
                value['peakMises']=records[key]['peakMises'];value['peakPoint']=records[key]['peakPoint']
            report['reportedForJob']=job
            answer['verificationStudy']=report
            answer['validation']['meshConvergence']='scoped_in_verificationStudy'
            answer['validation']['cutLengthSensitivity']='passed' if report['cutPassed'] else 'failed'
            answer['result']['convergenceStatus']='see_verificationStudy'
    return answer


def job_directory(job_id):
    if not re.fullmatch('[0-9a-f]{32}',job_id):
        raise ValueError('无效的作业编号。')
    path = RUN_ROOT/job_id
    if not path.is_dir():
        raise ValueError('作业不存在。')
    return path


def suggest(request):
    from framecae.local_analysis.critical_node import rank_critical_nodes
    model=payload_to_model(request.get('model'))
    result=StaticSolver(method='scipy').solve(model)
    candidates=[int(request['node'])] if request.get('node') else [r.node_id for r in rank_critical_nodes(model,result)]
    errors=[]
    for node in candidates:
        try:
            q=prepare({'model':request['model'],'settings':{'node':node}})
            return {'node':node,'geometry':q['geometry'],'mesh':q['mesh'],'schemaVersion':q['schemaVersion'],
                    'armCount':len(q['arms']),'arms':q['arms'],'geometryPrecheck':q.get('geometryPrecheck'),
                    'cutLength':q['arms'][0]['length'],'load':q['load'],'warnings':q['warnings'],
                    'message':f'已读取 N{node} 的 {len(q["arms"])} 个圆管杆端、切口运动和节点外载；图 B 尺寸采用演示初值。'}
        except ValueError as error: errors.append(str(error))
    raise ValueError('没有通过图B几何检查的非支座节点：'+('; '.join(dict.fromkeys(errors)))[:1000])


def start(request):
    prepared = prepare(request)
    if not LAUNCHER.is_file():
        raise ValueError(f'Abaqus 启动器不存在：{LAUNCHER}')
    RUN_ROOT.mkdir(parents=True,exist_ok=True)
    # Submission is cheap; actual solver processes are serialized by the worker lock.
    job = uuid.uuid4().hex
    path = RUN_ROOT/job
    path.mkdir()
    atomic_json(path/'local_request.json',prepared)
    atomic_json(path/'status.json',{'jobId':job,'state':'queued','message':'已排队，等待本机 Abaqus',
                                 'fingerprint':prepared['fingerprint'],'createdAt':datetime.now(timezone.utc).isoformat()})
    env = dict(os.environ)
    env['PYTHONPATH'] = str(PROJECT)+os.pathsep+env.get('PYTHONPATH','')
    flags = subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with (path/'worker.log').open('ab') as log:
        subprocess.Popen([sys.executable,'-m','framecae.abaqus_local.worker',str(path)],cwd=str(PROJECT),
                         env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=flags)
    return status(job)


def status(job):
    path=job_directory(job)
    result=json.loads((path/'status.json').read_text('utf-8'))
    result['directory']=str(path)
    result['files']=[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(path.iterdir()) if p.is_file()]
    result['hasResult']=result['state']=='completed' and (path/'local_results.json').is_file()
    log=path/'abaqus.log'
    if log.exists():
        result['logTail']=log.read_bytes()[-4000:].decode('gb18030',errors='replace')
    return result


def artifact(job,name):
    path=job_directory(job)
    allowed={'local_request.json','local_results.json','model.inp','model.odb','model.cae',
             'mesh.json','mesh_meta.json','validation.json','stress.csv','displacement.csv',
             'model.sta','model.msg','model.dat','abaqus.log','status.json','toe_samples.json','toe_validation.json'}
    if name not in allowed or not (path/name).is_file():
        raise ValueError('该作业文件不存在或不允许下载。')
    return path/name
