"""FrameCAE 本机浏览器界面服务。"""

from __future__ import annotations

import json
import mimetypes
import os
import webbrowser
import zipfile
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from framecae.io.payload import (
    default_payload,
    initial_payload,
    course_verification_payload,
    local_t_joint_demo_payload,
    solve_local_t_joint_convergence_payload,
    solve_local_t_joint_payload,
    solve_generic_tubular_node_payload,
    solve_generic_tubular_node_convergence_payload,
    solve_payload,
    strength_check_payload,
    stability_check_payload,
    suggest_generic_tubular_node_settings,
    suggest_t_joint_settings,
)
from framecae.optimization.frame_full_stress import optimize_frame_full_stress
from framecae.ai_modeling import propose_model, review_model_request
from framecae.manual_reconstruction.reconstruction import load_calibration, reconstruct
from framecae.manual_reconstruction.rod_inference import infer_rods
from framecae.manual_reconstruction.adapter import build_framecae_draft
from framecae.abaqus_local import service as abaqus_local
from framecae.solid_local import service as solid_local
from framecae import abaqus_verify

WEB_ROOT = Path(__file__).with_name("web")
PAGE_TEMPLATE = WEB_ROOT / "index.html"
# This integration round excludes Abaqus validation. Keep its implementation
# intact for colleagues; re-enable this switch explicitly when needed.
ABAQUS_VERIFICATION_ENABLED = False

_GENERIC_CONVERGENCE_INPUT_REPAIR = """
<script>
(() => {
  const repair = () => {
    const count = document.querySelector('#genericSampleCount');
    const limit = document.querySelector('#genericMaxDofs');
    if (count && !/^[3-6]$/.test(String(count.value).trim())) count.value = '6';
    const dofs = limit ? Number(limit.value) : NaN;
    if (limit && (!Number.isSafeInteger(dofs) || dofs < 30000 || dofs > 300000)) limit.value = '300000';
  };
  const install = () => {
    repair();
    ['#autoGeneric', '#selectedGeneric'].forEach(selector => {
      document.querySelector(selector)?.addEventListener('click', () => {
        window.setTimeout(repair, 0); window.setTimeout(repair, 600);
      });
    });
    document.querySelector('#runGenericConvergence')?.addEventListener('click', repair, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})();
</script>
"""


class FrameCAEHandler(BaseHTTPRequestHandler):
    """只提供本机静态页面及默认模型、求解两个 API。"""

    def do_GET(self) -> None:  # noqa: N802
        request_path = urlsplit(self.path).path
        if request_path == '/api/image-reconstruction/calibration':
            try:
                calibration = load_calibration()
                calibration.update({'min_baseline_matches': 7, 'interface_version': 4})
                return self._send_json(calibration)
            except (OSError, KeyError, ValueError) as error:
                return self._send_json({'error': f'无法读取相机标定：{error}'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        image_assets = {'/image-reconstruction/': 'index.html',
                        '/image-reconstruction/app.js': 'app.js',
                        '/image-reconstruction/style.css': 'style.css'}
        if request_path in image_assets:
            return self._send_file(WEB_ROOT / 'manual-reconstruction' / image_assets[request_path])
        if request_path == '/api/archive/cases':
            from framecae.archive_layout import catalog
            return self._send_json(catalog())
        if request_path == '/archive-cases-panel.js':
            return self._send_file(WEB_ROOT / 'archive-cases-panel.js')
        if request_path == '/api/examples/textbook-progress':
            from framecae.textbook_cases import progress
            return self._send_json(progress())
        if request_path == '/api/examples/textbook':
            from framecae.textbook_cases import catalog
            return self._send_json(catalog())
        if request_path.startswith('/api/examples/textbook/'):
            from framecae.textbook_cases import detail
            try:
                return self._send_json(detail(request_path.rsplit('/', 1)[-1]))
            except (ValueError, StopIteration, OSError) as error:
                return self._send_json({'error': str(error)}, status=HTTPStatus.BAD_REQUEST)
        if request_path == '/textbook-cases-panel.js':
            return self._send_file(WEB_ROOT / 'textbook-cases-panel.js')
        if request_path=='/api/local-t-demo':
            return self._send_json({'error':'本发行版只提供03截面内力驱动。'},status=HTTPStatus.GONE)
        if request_path=='/api/empty':
            return self._send_json(initial_payload())
        if request_path.startswith('/api/abaqus-verify/'):
            return self._verify_get(request_path)
        if request_path == '/abaqus-verify-panel.js':
            return self._send_file(WEB_ROOT / 'abaqus-verify-panel.js')
        if request_path.startswith('/api/solid-local/'):
            return self._solid_get(request_path)
        if request_path in ('/solid-local-panel.js','/solid-view.js','/vendor/plotly.min.js'):
            return self._send_file(WEB_ROOT/request_path.lstrip('/'))
        if request_path.startswith('/api/abaqus-local/'):
            try:
                parts=request_path.strip('/').split('/')
                if parts==['api','abaqus-local','environment']:
                    self._send_json({'available':abaqus_local.LAUNCHER.is_file(),'launcher':str(abaqus_local.LAUNCHER)})
                elif parts==['api','abaqus-local','verified-case']:
                    case=WEB_ROOT.parent/'verification'/'weld_toe'/'recommended_case.json'
                    if not case.is_file():raise ValueError('圆管焊趾验证尚未完成。')
                    self._send_file(case)
                elif len(parts)>=4 and parts[2]=='jobs':
                    job=parts[3]
                    if len(parts)==4:
                        self._send_json(abaqus_local.status(job))
                    elif len(parts)==5 and parts[4]=='result':
                        if not abaqus_local.status(job)['hasResult']:
                            raise ValueError('作业尚未成功完成。')
                        self._send_json(abaqus_local.verified_result(job))
                    elif len(parts)==6 and parts[4]=='files':
                        path=abaqus_local.artifact(job,parts[5])
                        self.send_response(HTTPStatus.OK)
                        self.send_header('Content-Type','application/octet-stream')
                        self.send_header('Content-Disposition','attachment; filename="'+path.name+'"')
                        self.send_header('Content-Length',str(path.stat().st_size))
                        self.end_headers()
                        import shutil
                        with path.open('rb') as stream: shutil.copyfileobj(stream,self.wfile)
                    else: self.send_error(HTTPStatus.NOT_FOUND)
                else: self.send_error(HTTPStatus.NOT_FOUND)
            except (ValueError,OSError) as error:
                self._send_json({'error':str(error)},status=HTTPStatus.BAD_REQUEST)
        elif request_path == '/api/features':
            self._send_json({'abaqusVerificationEnabled': ABAQUS_VERIFICATION_ENABLED})
        elif request_path in ('/abaqus-local-panel.js', '/model-view.js', '/member-load-panel.js','/force-only-policy.js'):
            self._send_file(WEB_ROOT/request_path.lstrip('/'))
        elif request_path in ("/", "/index.html"):
            self._send_page_template("text/html; charset=utf-8")
        elif self.path == "/strength-panel.js":
            self._send_file(WEB_ROOT / "strength-panel.js")
        elif self.path == "/selfweight-panel.js":
            self._send_file(WEB_ROOT / "selfweight-panel.js")
        elif self.path == "/assembly-panel.js":
            self._send_file(WEB_ROOT / "assembly-panel.js")
        elif self.path == "/stability-panel.js":
            self._send_file(WEB_ROOT / "stability-panel.js")
        elif self.path == "/full-stress-panel.js":
            self._send_file(WEB_ROOT / "full-stress-panel.js")
        elif self.path == "/visual-builder.js":
            self._send_file(WEB_ROOT / "visual-builder.js")
        elif self.path == "/module-hub.js":
            self._send_file(WEB_ROOT / "module-hub.js")
        elif self.path == "/workspace-ui.js":
            self._send_file(WEB_ROOT / "workspace-ui.js")
        elif self.path == "/workspace.css":
            self._send_file(WEB_ROOT / "workspace.css")
        elif request_path == "/api-client.js":
            self._send_file(WEB_ROOT / "api-client.js")
        elif request_path == "/local-report.js":
            self._send_file(WEB_ROOT / "local-report.js")
        elif request_path == "/local-report.css":
            self._send_file(WEB_ROOT / "local-report.css")
        elif request_path in ("/visual-workbench.js", "/visual-workbench.css"):
            self._send_file(WEB_ROOT / request_path.lstrip("/"))
        elif request_path == "/api/health":
            self._send_json({"application": "FrameCAE", "status": "ok",'features':['abaqusLocalHubV1','circularToeV2','standaloneTet10V1','continuousPipePatchV1','idealClampV1','archiveCasesV1','interactiveXYZ3D','aiClarificationV1','calibratedImageReconstructionV3','fullStressV1','fullStressFrameV2'],'project':str(WEB_ROOT.parent)})
        elif request_path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        elif self.path == "/local-cloud.js":
            self._send_file(WEB_ROOT / "local-cloud.js")
        elif self.path == "/internal-force-panel.js":
            self._send_file(WEB_ROOT / "internal-force-panel.js")
        elif self.path == "/welded-node-panel.js":
            self._send_file(WEB_ROOT / "welded-node-panel.js")
        elif self.path == "/ai-modeling-panel.js":
            self._send_file(WEB_ROOT / "ai-modeling-panel.js")
        elif request_path == "/image-reconstruction-panel.js":
            self._send_file(WEB_ROOT / "image-reconstruction-panel.js")
        elif self.path == "/modal-editor.js":
            self._send_file(WEB_ROOT / "modal-editor.js")
        elif self.path == "/api/default":
            self._send_json(default_payload())
        elif self.path == "/beam-curve.js":
            self._send_file(WEB_ROOT / "beam-curve.js")
        elif self.path == "/deformation-view.js":
            self._send_file(WEB_ROOT / "deformation-view.js")
        elif self.path == "/api/local-t-demo":
            self._send_json(local_t_joint_demo_payload())
        else:
            # ``BaseHTTPRequestHandler`` 的状态行只能编码 latin-1；浏览器
            # 请求 favicon 等不存在资源时不能把中文说明直接传给 send_error。
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == '/api/archive/save':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 20_000_000:
                    raise ValueError('保存内容大小无效。')
                from framecae.archive_layout import save_results
                return self._send_json(save_results(json.loads(self.rfile.read(length).decode('utf-8'))))
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._send_json({'error': str(error)}, status=HTTPStatus.BAD_REQUEST)
        if self.path in ('/api/local-t-joint','/api/local-t-convergence','/api/local-t-suggest','/api/local-generic-node','/api/local-generic-suggest','/api/local-generic-convergence'):
            return self._send_json({'error':'请使用03自编截面内力驱动接口。'},status=HTTPStatus.GONE)
        if not ABAQUS_VERIFICATION_ENABLED and (self.path.startswith('/api/abaqus-verify/') or
                self.path in ('/api/abaqus-local/jobs','/api/abaqus-local/prepare','/api/abaqus-local/suggest')):
            return self._send_json({'error':'本轮已禁用Abaqus验算；03请使用自编有限元。原验算代码保留。'}, status=HTTPStatus.FORBIDDEN)
        if self.path.startswith('/api/abaqus-verify/'):
            return self._verify_post()
        if self.path.startswith('/api/solid-local/'):
            return self._solid_post()
        if self.path not in {
            "/api/solve", "/api/verification", "/api/local-t-joint", "/api/local-t-convergence",
            "/api/local-t-suggest", "/api/local-generic-node", "/api/local-generic-suggest", "/api/local-generic-convergence",
            "/api/strength-check", "/api/stability-check", "/api/full-stress", "/api/ai-model-questions", "/api/ai-model-draft",
            "/api/image-reconstruction/reconstruct", "/api/image-reconstruction/infer-rods", "/api/image-reconstruction/draft",
            '/api/abaqus-local/prepare','/api/abaqus-local/jobs','/api/abaqus-local/suggest','/api/abaqus-local/circular-sections',
        }:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path.startswith('/api/image-reconstruction/'):
                limit = 16_000_000 if self.path == '/api/image-reconstruction/infer-rods' else 1_000_000
                if length <= 0 or length > limit:
                    raise ValueError('图像建模提交的数据为空或过大。')
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path=='/api/abaqus-local/circular-sections':
                response=abaqus_local.circular_sections(payload)
            elif self.path=='/api/abaqus-local/prepare':
                response=abaqus_local.prepare(payload)
            elif self.path=='/api/abaqus-local/jobs':
                response=abaqus_local.start(payload)
            elif self.path=='/api/abaqus-local/suggest':
                response=abaqus_local.suggest(payload)
            elif self.path == "/api/solve":
                response = solve_payload(payload)
            elif self.path == "/api/verification":
                response = course_verification_payload()
            elif self.path == "/api/local-t-joint":
                response = solve_local_t_joint_payload(payload)
            elif self.path == "/api/local-t-convergence":
                response = solve_local_t_joint_convergence_payload(payload)
            elif self.path == "/api/local-generic-node":
                response = solve_generic_tubular_node_payload(payload)
            elif self.path == "/api/local-generic-convergence":
                response = solve_generic_tubular_node_convergence_payload(payload)
            elif self.path == "/api/local-generic-suggest":
                response = suggest_generic_tubular_node_settings(payload)
            elif self.path == "/api/strength-check":
                response = strength_check_payload(payload)
            elif self.path == "/api/stability-check":
                response = stability_check_payload(payload)
            elif self.path == "/api/full-stress":
                response = optimize_frame_full_stress(payload)
            elif self.path == "/api/ai-model-questions":
                response = review_model_request(payload.get("prompt"), payload.get("baseModel"))
            elif self.path == "/api/ai-model-draft":
                response = propose_model(payload.get("prompt"), payload.get("baseModel"),
                                         confirmed_parameters=payload.get("confirmedParameters"))
            elif self.path == "/api/image-reconstruction/reconstruct":
                response = reconstruct(payload)
            elif self.path == "/api/image-reconstruction/infer-rods":
                response = infer_rods(payload)
            elif self.path == "/api/image-reconstruction/draft":
                response = build_framecae_draft(payload)
            else:
                response = suggest_t_joint_settings(payload)
            self._send_json(response)
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except ModuleNotFoundError as error:
            self._send_json({"error": f"缺少运行依赖 {error.name}。请使用“启动FrameCAE.cmd”安装依赖后重启。"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
        except Exception as error:  # Keep local browser failures diagnosable.
            self._send_json({"error": f"本机后端处理失败：{type(error).__name__}: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_page_template(self, content_type: str) -> None:
        """读取独立页面模板并注入当前模块脚本。"""
        try:
            content = PAGE_TEMPLATE.read_bytes()
        except (FileNotFoundError, KeyError, zipfile.BadZipFile):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if content_type.startswith("text/html"):
            html=content.decode('utf-8')
            html=html.replace('</head>', '<script>window.FRAMECAE_ABAQUS_VERIFICATION_ENABLED='+json.dumps(ABAQUS_VERIFICATION_ENABLED)+'</script></head>')
            html=re.sub(r'async function loadDefault\(\)\{[^\n]*\}',
                "async function loadDefault(){const response=await fetch('/api/empty');if(!response.ok)throw Error('无法加载初始模型。');data=await response.json();result=null;localResult=null;convergenceResult=null;displayMode='global';renderTables();document.querySelector('#results').textContent='已预置可编辑的材料和圆管截面，请导入模型 JSON 或开始建模。';document.querySelector('#status').textContent='空白画布已就绪，材料与截面已有初始值。';draw()}",html,count=1)
            html=html.replace('await loadDefault();await solve()', 'await loadDefault()')
            content = html.replace(
                ",span=Math.max(...high.map((v,i)=>v-low[i]),1),pixels=Math.min(width,height)*.38/span*view.zoom",
                ",span=Math.max(...high.map((v,i)=>v-low[i]),1e-9),pixels=Math.min(width,height)*.56/span*view.zoom",
            ).replace(
                "</head>", '<script src="/api-client.js"></script><script src="/model-view.js"></script></head>',
            ).replace(
                "</body>", _GENERIC_CONVERGENCE_INPUT_REPAIR + '<script src="/selfweight-panel.js"></script><script src="/assembly-panel.js"></script><script src="/strength-panel.js"></script><script src="/stability-panel.js"></script><script src="/full-stress-panel.js"></script><script src="/visual-builder.js"></script><script src="/internal-force-panel.js"></script><script src="/module-hub.js"></script><script src="/local-cloud.js"></script><script src="/welded-node-panel.js"></script><script src="/ai-modeling-panel.js"></script><script src="/image-reconstruction-panel.js"></script></body>',
            ).replace("</body>", '<script src="/beam-curve.js"></script><script src="/deformation-view.js"></script><script src="/workspace-ui.js"></script><script src="/local-report.js"></script><script src="/visual-workbench.js"></script><script src="/abaqus-local-panel.js"></script><script src="/vendor/plotly.min.js"></script><script src="/solid-view.js"></script><script src="/solid-local-panel.js"></script><script src="/abaqus-verify-panel.js"></script><script src="/member-load-panel.js"></script><script src="/force-only-policy.js"></script><script src="/archive-cases-panel.js"></script></body>').encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _: str, *args: object) -> None:
        """不向终端输出每个浏览器资源请求。"""

    def _verify_get(self, path):
        try:
            parts = path.strip('/').split('/')
            if parts == ['api', 'abaqus-verify', 'environment']:
                return self._send_json(abaqus_verify.environment())
            if len(parts) >= 4 and parts[:3] == ['api', 'abaqus-verify', 'jobs']:
                if len(parts) == 4:
                    return self._send_json(abaqus_verify.status(parts[3]))
                if len(parts) == 6 and parts[4] == 'files':
                    file = abaqus_verify.artifact(parts[3], parts[5])
                    self.send_response(HTTPStatus.OK)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Disposition', 'attachment; filename="' + file.name + '"')
                    self.send_header('Content-Length', str(file.stat().st_size))
                    self.end_headers()
                    import shutil
                    with file.open('rb') as stream:
                        shutil.copyfileobj(stream, self.wfile)
                    return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, OSError, KeyError) as error:
            self._send_json({'error': str(error)}, status=HTTPStatus.BAD_REQUEST)

    def _verify_post(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8_000_000:
                raise ValueError('请求大小无效。')
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            parts = urlsplit(self.path).path.strip('/').split('/')
            if parts == ['api', 'abaqus-verify', 'jobs']:
                answer = abaqus_verify.create(payload)
            elif len(parts) == 5 and parts[:3] == ['api', 'abaqus-verify', 'jobs'] and parts[4] == 'solve':
                answer = abaqus_verify.solve(parts[3])
            elif len(parts) == 5 and parts[:3] == ['api', 'abaqus-verify', 'jobs'] and parts[4] == 'viewer':
                answer = abaqus_verify.open_viewer(parts[3])
            else:
                return self.send_error(HTTPStatus.NOT_FOUND)
            self._send_json(answer)
        except (ValueError, OSError, KeyError, TypeError) as error:
            self._send_json({'error': str(error)}, status=HTTPStatus.BAD_REQUEST)

    def _solid_get(self,path):
        try:
            parts=path.strip('/').split('/')
            if parts==['api','solid-local','environment']:return self._send_json(solid_local.environment())
            if len(parts)>=4 and parts[2]=='jobs':
                job=parts[3]
                if len(parts)==4:return self._send_json(solid_local.status(job))
                if len(parts)==5 and parts[4]=='result':return self._send_json(solid_local.result(job))
                if len(parts)==6 and parts[4]=='files':return self._send_file(solid_local.artifact(job,parts[5]))
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError,OSError,KeyError) as error:self._send_json({'error':str(error)},status=HTTPStatus.BAD_REQUEST)

    def _solid_post(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8_000_000:raise ValueError('请求大小无效。')
            payload=json.loads(self.rfile.read(length).decode('utf-8'))
            parts=urlsplit(self.path).path.strip('/').split('/')
            if parts==['api','solid-local','suggest']:answer=solid_local.suggest(payload)
            elif parts==['api','solid-local','prepare']:answer=solid_local.prepare(payload)
            elif parts==['api','solid-local','jobs']:answer=solid_local.start(payload)
            elif len(parts)==5 and parts[2]=='jobs' and parts[4]=='cancel':answer=solid_local.cancel(parts[3])
            else:return self.send_error(HTTPStatus.NOT_FOUND)
            self._send_json(answer)
        except (ValueError,OSError,KeyError,TypeError) as error:self._send_json({'error':str(error)},status=HTTPStatus.BAD_REQUEST)


def main() -> None:
    # A stable local address prevents browser tabs from retaining an obsolete random port after restart.
    port = int(os.environ.get("FRAMECAE_PORT", "50077"))
    server = ThreadingHTTPServer(("127.0.0.1", port), FrameCAEHandler)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"FrameCAE 本机界面已启动：{address}")
    print("关闭此终端窗口即可停止服务。")
    webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
