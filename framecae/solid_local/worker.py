"""Disk-backed cancellable worker; serial by default, bounded opt-in slots."""
import copy,json,os,sys,time,traceback,shutil,subprocess
from pathlib import Path
from .service import atomic_json, RUN_ROOT

class Cancelled(Exception):pass

def run(directory):
    directory=Path(directory);meta=json.loads((directory/'status.json').read_text('utf-8'));lock=None
    labels={'building':'建立 B 实体与曲边网格','assembling':'装配曲边 Tet10 刚度','preconditioning':'构造稀疏预条件器','solving':'求解位移','recovering':'恢复应力','checking':'核对焊趾、肩部与平衡','exporting':'生成原网页云图与导出文件'}
    def update(state,**info):
        if (directory/'cancel.request').exists():raise Cancelled()
        meta.update(state=state,message=labels.get(state,state));meta.update(info);atomic_json(directory/'status.json',meta)
    try:
        if os.name=='nt':
            import msvcrt
            slots=max(1,min(int(os.environ.get('FRAMECAE_SOLID_WORKERS','1')),4))
            while True:
                if (directory/'cancel.request').exists():raise Cancelled()
                for slot in range(slots):
                    filename='solid_solver.lock' if slot==0 else 'solid_solver_%d.lock'%slot
                    handle=(RUN_ROOT/filename).open('a+b');handle.seek(0);handle.write(b'0');handle.flush()
                    try:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);lock=handle;break
                    except OSError:handle.close()
                if lock:break
                time.sleep(.3)
        from .analysis import solve
        from . import toes,shoulders
        from .result_adapter import adapt
        from .exports import export
        request=json.loads((directory/'local_request.json').read_text('utf-8'))
        study=json.loads((directory/'study_request.json').read_text('utf-8')) if (directory/'study_request.json').exists() else None
        sizes=study['toeSizes'] if study else [request['mesh']['toeSize']]
        records=[];last=None
        for index,h in enumerate(sizes):
            work=directory/('case_'+str(index+1)) if study else directory;work.mkdir(exist_ok=True)
            q=copy.deepcopy(request);q['mesh']['toeSize']=h
            atomic_json(work/'local_request.json',q)
            update('building',sample=index+1,samples=len(sizes),toeSizeM=h)
            from .geometry_cache import reuse
            reused=reuse(work,q) if not study else None
            if reused:
                code=0;update('building',meshReusedFrom=reused);print('REUSED_GEOMETRY_ONLY',reused,flush=True)
            else:
                child=subprocess.Popen([sys.executable,'-u','-m','framecae.solid_local.geometry_cli',str(work)],
                    cwd=Path(__file__).resolve().parents[2],stdout=sys.stdout,stderr=sys.stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:code=child.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    child.kill();child.wait();raise RuntimeError('实体建模/网格超过30分钟，已终止。')
            if code:
                detail=(work/'geometry_error.txt').read_text('utf-8').splitlines()[-1] if (work/'geometry_error.txt').exists() else '原生网格进程异常退出；详见 worker.log'
                raise RuntimeError('实体网格未完成 (exit %s): %s'%(code,detail))
            mesh_meta=json.loads((work/'mesh_meta.json').read_text('utf-8'))
            limit=int(os.environ.get('FRAMECAE_SOLID_MAX_NODES','1000000'))
            if mesh_meta['nodes']>limit:raise ValueError(f"网格包含 {mesh_meta['nodes']} 个节点，超出本机当前上限 {limit}；请增大网格尺寸后重试。")
            solve(work,q,progress=update)
            if (work/'resolved_request.json').exists():q=json.loads((work/'resolved_request.json').read_text('utf-8'))
            update('checking')
            if q.get('analysisType') in ('continuousPipe','idealClamp'):
                from .line_samples import analyze as analyze_line
                toe=analyze_line(work,q);shoulder={}
            else:toe=toes.analyze(work,q);shoulder=shoulders.analyze(work,q)
            raw=json.loads((work/'result.json').read_text('utf-8'))
            records.append(dict(toeSizeM=h,toes=toe,shoulders=shoulder,maximumElementNodalMisesPa=raw['maximumElementNodalMisesPa']))
            last=work
        update('exporting');answer=adapt(last,q,meta['jobId'])
        if not answer['validation']['numericalPassed']:raise RuntimeError('数值残差或平衡检查未通过；结果保留用于排查，未标记为成功。')
        answer['fingerprint']=request['fingerprint'];answer['resolvedLocalRequest']=q;answer['localRequest']=request;answer['actualMesh']=q['mesh']
        if study:
            comparison=toes.compare(directory/('case_'+str(len(sizes)-1)),last)
            study_result=dict(kind='weldToeMesh',cases=records,lastPair=comparison,cutLengthM=answer['result']['cutLength'],scope='仅焊趾局部网格；肩部网格保持不变，截断距离未比较。')
            if q.get('analysisType'):
                study_result.update(kind='pipeRegionMesh',scope='固定连续圆管关注区域的局部网格比较；加载面片保持不变，截取距离另行比较。')
            answer['verificationStudy']=study_result;answer['validation']['meshConvergence']=comparison
            atomic_json(directory/'study.json',study_result)
        export(last,q)
        shutil.copy2(Path(__file__).with_name('export_odb.py'),directory/'export_odb.py')
        if last!=directory:
            for name in ('mesh.npz','solution.npz','mesh_meta.json','validation.json','toe_results.json','toe_samples.npz','shoulder_results.json','mesh.msh','geometry.step','model.inp','result.vtu','stress.csv'):
                if (last/name).exists():
                    try:os.link(last/name,directory/name)
                    except OSError:shutil.copy2(last/name,directory/name)
        atomic_json(directory/'local_results.json',answer);atomic_json(directory/'validation.json',answer['validation'])
        update('completed',message='独立有限元计算完成；各项验证状态分别列出。',summary=answer['result'],validation=answer['validation'])
    except Cancelled:
        meta.update(state='cancelled',message='计算已取消。');atomic_json(directory/'status.json',meta)
    except BaseException as e:
        (directory/'worker_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print(traceback.format_exc(),flush=True);meta.update(state='failed',message=str(e));atomic_json(directory/'status.json',meta)
    finally:
        if lock:
            try:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            except OSError:pass
            lock.close()

if __name__=='__main__':run(sys.argv[1])
