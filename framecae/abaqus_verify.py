"""Two-stage Abaqus verification of the exact standalone local model."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from framecae.solid_local import service as solid

PROJECT = Path(__file__).resolve().parents[1]
from framecae.abaqus_launcher import find_launcher
LAUNCHER = find_launcher()
RUN_ROOT = Path(os.environ.get('FRAMECAE_ABAQUS_VERIFY_RUNS', r'D:\AbaqusWork\framecae03\verify'))
FILES = {'model.inp', 'verify.odb', 'verify.sta', 'verify.msg', 'verify.dat',
         'abaqus.log', 'worker.log', 'mesh_meta.json', 'comparison.json',
         'local_request.json', 'worker_error.txt'}


def environment():
    return {'available': LAUNCHER.is_file(), 'launcher': str(LAUNCHER),
            'message': 'Abaqus 启动器已找到。' if LAUNCHER.is_file() else '未找到 Abaqus 启动器；可设置 ABAQUS_LAUNCHER。'}


def job_dir(job):
    if not re.fullmatch(r'[0-9a-f]{32}', str(job)):
        raise ValueError('作业编号无效。')
    path = RUN_ROOT / job
    if not path.is_dir():
        raise ValueError('未找到 Abaqus 验证作业。')
    return path


def status(job):
    path = job_dir(job)
    data = json.loads((path / 'status.json').read_text(encoding='utf-8'))
    data['files'] = sorted(name for name in FILES if (path / name).is_file())
    data['hasInp'] = (path / 'model.inp').is_file()
    data['hasOdb'] = data['state'] == 'completed' and (path / 'verify.odb').is_file()
    if (path / 'comparison.json').is_file():
        data['comparison'] = json.loads((path / 'comparison.json').read_text(encoding='utf-8'))
    return data


def artifact(job, name):
    if name not in FILES:
        raise ValueError('不允许读取该文件。')
    path = job_dir(job) / name
    if not path.is_file():
        raise ValueError('文件尚未生成。')
    return path


def _spawn(path, phase):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        env[name] = '1'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (path / 'worker.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, '-u', '-m', 'framecae.abaqus_verify_worker',
                                    str(path), phase], cwd=PROJECT, env=env, stdout=log,
                                   stderr=log, stdin=subprocess.DEVNULL, creationflags=flags)
    return process.pid


def create(payload):
    request = solid.prepare(payload)
    if not solid.environment()['available']:
        raise ValueError('缺少几何和网格生成依赖。')
    preferred = payload.get('sourceJobId')
    source = None
    if preferred:
        record = solid.status(preferred)
        saved=json.loads((solid.job_directory(preferred)/'local_request.json').read_text('utf-8'))
        if record['state'] != 'completed' or solid.physical_key(saved) != solid.physical_key(request):
            raise ValueError('所选自编作业与当前模型不一致，无法复用网格。')
        source = solid.job_directory(preferred)
        if not (source / 'model.inp').is_file():
            raise ValueError('所选自编作业缺少 model.inp。')
    else:
        # Reuse a completed job with the same immutable input when possible.
        if solid.RUN_ROOT.is_dir():
            for folder in solid.RUN_ROOT.iterdir():
                if not folder.is_dir():
                    continue
                try:
                    record = solid.status(folder.name)
                    saved=json.loads((folder/'local_request.json').read_text('utf-8'))
                    if (record['state'] == 'completed' and
                            solid.physical_key(saved) == solid.physical_key(request) and
                            (folder / 'model.inp').is_file()):
                        source = folder
                        break
                except (ValueError, OSError, KeyError):
                    continue
    if request.get('couplingMode')=='compatible' and source is None:
        raise ValueError('协调边界方式请先完成自编求解，再复用其协调切口运动生成 INP。')
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    job = uuid.uuid4().hex
    path = RUN_ROOT / job
    path.mkdir()
    solid.atomic_json(path / 'local_request.json', request)
    solid.atomic_json(path / 'source.json', {'path': str(source) if source else None})
    state = {'jobId': job, 'state': 'generating', 'message':
             '正在复用自编网格和 INP。' if source else '正在建立曲边 Tet10 网格并生成 INP。',
             'fingerprint': request['fingerprint'], 'sourceJobId': source.name if source else None,
             'createdAt': datetime.now(timezone.utc).isoformat()}
    solid.atomic_json(path / 'status.json', state)
    try:
        _spawn(path, 'generate')
    except BaseException:
        state.update(state='failed', message='无法启动 INP 生成进程。')
        solid.atomic_json(path / 'status.json', state)
        raise
    return state


def solve(job):
    path = job_dir(job)
    state = status(job)
    if state['state'] != 'inp_ready' or not state['hasInp']:
        raise ValueError('请先生成 INP，且不要重复提交同一作业。')
    if not LAUNCHER.is_file():
        raise ValueError('找不到 Abaqus 启动器：' + str(LAUNCHER))
    for key in ('files', 'hasInp', 'hasOdb', 'comparison'):
        state.pop(key, None)
    state.update(state='solving', message='Abaqus/Standard 正在求解。')
    solid.atomic_json(path / 'status.json', state)
    try:
        _spawn(path, 'solve')
    except BaseException:
        state.update(state='inp_ready', message='无法启动 Abaqus 作业，可重试。')
        solid.atomic_json(path / 'status.json', state)
        raise
    return state


def open_viewer(job):
    state = status(job)
    if not state['hasOdb']:
        raise ValueError('Abaqus 尚未成功生成 ODB。')
    if not LAUNCHER.is_file():
        raise ValueError('找不到 Abaqus 启动器。')
    from framecae.abaqus_local.worker import command
    path = job_dir(job)
    # Viewer is a desktop application: keep its process visible and detached.
    with (path / 'viewer.log').open('ab') as log:
        process = subprocess.Popen(command(['viewer', 'database=verify.odb']), cwd=path,
                                   stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                   creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0))
    return {'opened': True, 'jobId': job, 'viewerPid': process.pid, 'odb': str(path / 'verify.odb')}
