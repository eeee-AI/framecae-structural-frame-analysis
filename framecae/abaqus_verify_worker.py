"""Generate an Abaqus input independently, then run Abaqus/Standard."""
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from framecae.abaqus_verify import LAUNCHER
from framecae.abaqus_local.worker import command
from framecae.solid_local.service import atomic_json


def write_inp(path, request):
    """Optional export of a completed force submodel; no kinematic fallback."""
    if request.get('couplingMode')!='forceSubmodel':raise ValueError('Only section-resultant models are supported')
    if not (path/'solution.npz').is_file():raise ValueError('请先完成自编截面内力求解，再导出对应载荷与刚体定姿。')
    from framecae.solid_local.exports import export
    export(path,request)


def run(folder, phase):
    path = Path(folder)
    state = json.loads((path / 'status.json').read_text(encoding='utf-8'))
    def update(name, message):
        state.update(state=name, message=message)
        atomic_json(path / 'status.json', state)
    try:
        if phase == 'generate':
            request = json.loads((path / 'local_request.json').read_text(encoding='utf-8'))
            source = json.loads((path / 'source.json').read_text(encoding='utf-8'))['path']
            if source:
                source = Path(source)
                saved = json.loads((source / 'local_request.json').read_text(encoding='utf-8'))
                from framecae.solid_local.service import physical_key
                if physical_key(saved) != physical_key(request):
                    raise ValueError('源网格对应的输入已变化。')
                for name in ('model.inp', 'mesh_meta.json'):
                    shutil.copy2(source / name, path / name)
                if (source/'resolved_request.json').exists():shutil.copy2(source/'resolved_request.json',path/'resolved_request.json')
            else:
                from framecae.solid_local.geometry import build
                mesh = request['mesh']
                meta = build(request, path, mesh['toeSize'], mesh['size'], mesh['focusSize'])
                if meta['nodes'] > int(os.environ.get('FRAMECAE_SOLID_MAX_NODES', '1000000')):
                    raise ValueError('网格超过节点上限，请调粗尺寸后重试。')
                write_inp(path, request)
            if not (path / 'model.inp').is_file() or (path / 'model.inp').stat().st_size < 100:
                raise ValueError('INP 生成失败。')
            update('inp_ready', 'INP 已生成，可下载检查并提交 Abaqus/Standard。')
        elif phase == 'solve':
            if not LAUNCHER.is_file():
                raise ValueError('Abaqus 启动器不存在。')
            memory = os.environ.get('FRAMECAE_ABAQUS_MEMORY', '35%')
            if not re.fullmatch(r'[1-9][0-9]*(?:%|mb|gb)', memory):
                raise ValueError('Abaqus 内存参数无效。')
            env = dict(os.environ)
            env['PATH'] = str(LAUNCHER.parent) + os.pathsep + env.get('PATH', '')
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            with (path / 'abaqus.log').open('ab') as log:
                process = subprocess.Popen(command(['job=verify', 'input=model.inp', 'cpus=2',
                                                    'memory=' + memory, 'interactive']), cwd=path,
                                           env=env, stdout=log, stderr=log,
                                           stdin=subprocess.DEVNULL, creationflags=flags)
                try:
                    code = process.wait(timeout=7200)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=log, stderr=log, creationflags=flags)
                    else:
                        process.kill()
                    raise RuntimeError('Abaqus 求解超过两小时。')
            if code:
                raise RuntimeError('Abaqus 返回错误码 %s；请查看 abaqus.log。' % code)
            sta = (path / 'verify.sta').read_text(errors='replace') if (path / 'verify.sta').is_file() else ''
            if ('THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in sta or
                    not (path / 'verify.odb').is_file() or (path / 'verify.lck').exists()):
                raise RuntimeError('Abaqus 未成功完成；请查看 verify.sta 和 verify.msg。')
            update('completed', 'Abaqus/Standard 已完成，ODB 已生成，可打开 Viewer。')
        else:
            raise ValueError('未知工作阶段。')
    except BaseException as error:
        (path / 'worker_error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        update('failed', str(error)[-3000:])


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
