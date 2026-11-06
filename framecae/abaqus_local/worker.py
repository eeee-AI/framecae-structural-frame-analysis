"""Detached, disk-backed worker. Only one local job builds/solves at a time."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys
import time
import traceback

from .service import atomic_json, LAUNCHER


def command(args):
    if any(c in str(LAUNCHER) for c in '"%\r\n!^&|<>'):
        raise ValueError('Unsupported characters in Abaqus launcher path')
    if os.name=='nt':
        return subprocess.list2cmdline([os.environ.get('COMSPEC',r'C:\Windows\System32\cmd.exe')])+ ' /d /s /c ""'+str(LAUNCHER)+'" '+subprocess.list2cmdline(args)+'"'
    return [str(LAUNCHER),*args]


def run(path):
    path=Path(path);meta=json.loads((path/'status.json').read_text('utf-8'))
    def update(state,message,**kwargs):
        meta.update(state=state,message=message,**kwargs);atomic_json(path/'status.json',meta)
    env=dict(os.environ)
    env.setdefault('COMSPEC',r'C:\Windows\System32\cmd.exe')
    env['PATH']=str(LAUNCHER.parent)+os.pathsep+env.get('PATH','')
    env['PYTHONIOENCODING']='utf-8'
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    lock=None
    try:
        if os.name=='nt':
            import msvcrt
            lock=(path.parent/'solver.lock').open('a+b')
            lock.seek(0);lock.write(b'0');lock.flush()
            while True:
                try:
                    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError: time.sleep(1)
        for filename in ('cae_build.py','mesh_ops.py','extract_odb.py'):
            shutil.copy2(Path(__file__).with_name(filename),path/filename)
        def execute(args):
            with (path/'abaqus.log').open('ab') as log:
                proc=subprocess.Popen(command(args),cwd=str(path),env=env,stdout=log,stderr=log,
                                      stdin=subprocess.DEVNULL,creationflags=flags)
                try: code=proc.wait(timeout=7200)
                except subprocess.TimeoutExpired:
                    if os.name=='nt': subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=log,creationflags=flags)
                    else: proc.kill()
                    raise RuntimeError('Abaqus stage exceeded two hours')
                if code: raise RuntimeError('Abaqus process returned %s; inspect abaqus.log'%code)
        local_request=json.loads((path/'local_request.json').read_text('utf-8'))
        update('building','正在建立一体节点件、%d道环焊缝及 C3D10 曲面网格'%len(local_request['arms']))
        execute(['cae','noGUI=cae_build.py','--','local_request.json'])
        if not (path/'build_result.json').is_file():
            detail=(path/'build_error.txt').read_text('utf-8') if (path/'build_error.txt').exists() else 'No build result'
            raise RuntimeError('实体建模未完成：'+detail.strip().splitlines()[-1])
        update('solving','网格与载荷已生成，Abaqus/Standard 正在求解',build=json.loads((path/'build_result.json').read_text('utf-8')))
        memory=env.get('FRAMECAE_ABAQUS_MEMORY','35%')
        if not re.fullmatch(r'[1-9][0-9]*(?:%|mb|gb)',memory):raise ValueError('Invalid Abaqus memory limit')
        execute(['job=model','input=model.inp','cpus=2','memory='+memory,'interactive'])
        sta=(path/'model.sta').read_text(errors='replace') if (path/'model.sta').exists() else ''
        if 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' not in sta or (path/'model.lck').exists() or not (path/'model.odb').exists():
            raise RuntimeError('Solver did not complete successfully; inspect model.sta/model.msg')
        update('extracting','求解成功，正在提取应力、位移和切口反力')
        execute(['python','extract_odb.py','model.odb'])
        if not (path/'local_results.json').is_file():
            raise RuntimeError('ODB extraction did not produce local_results.json')
        answer=json.loads((path/'local_results.json').read_text('utf-8'))
        if answer.get('kind')=='abaqusIntegralHub':
            from .toe_study import analyze
            sampled=analyze(path)
            answer['toePaths']=sampled['records'];answer['toeSampling']=sampled['sampling']
            atomic_json(path/'local_results.json',answer)
        update('completed','已完成，结果对应保存的本次输入快照',validation=answer['validation'],summary=answer['result'])
    except BaseException as error:
        (path/'worker_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        update('failed',str(error)[-4000:])
    finally:
        if lock:
            try:
                import msvcrt
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            except OSError: pass
            lock.close()


if __name__=='__main__': run(sys.argv[1])
