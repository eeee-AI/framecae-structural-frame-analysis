"""Start the app using the interpreter and libraries shipped in this folder."""
from pathlib import Path
import json
import os
import socket
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent


class ExclusiveFrameCAEServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    os.chdir(ROOT)
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    import framecae.solid_local
    import gmsh, skfem, pyamg, meshio, cv2
    import numpy
    import scipy
    from webapp import FrameCAEHandler

    state_file = ROOT / '.runtime-state.json'
    client = build_opener(ProxyHandler({}))
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding='utf-8'))
            with client.open(state['url'] + '/api/health', timeout=1) as response:
                health = json.load(response)
            if (health.get('application') == 'FrameCAE'
                    and Path(health.get('project', '')).resolve() == ROOT
                    and 'archiveCasesV1' in health.get('features', [])
                    and 'fullStressFrameV2' in health.get('features', [])):
                print('FrameCAE is already running: ' + state['url'], flush=True)
                if os.environ.get('FRAMECAE_NO_BROWSER') != '1':
                    webbrowser.open(state['url'])
                return
        except (OSError, ValueError, KeyError):
            pass
    preferred = int(os.environ.get('FRAMECAE_PORT', '62183'))
    server = None
    for port in [preferred, *range(62184, 62204), 0]:
        try:
            server = ExclusiveFrameCAEServer(('127.0.0.1', port), FrameCAEHandler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError('Cannot bind a local port')
    address = 'http://127.0.0.1:' + str(server.server_port)
    state_file.write_text(json.dumps({'url': address, 'pid': os.getpid()}, indent=2), encoding='utf-8')
    print('FrameCAE ready: ' + address, flush=True)
    print('Open this address in your browser. Close this window or press Ctrl+C to stop.', flush=True)
    if os.environ.get('FRAMECAE_NO_BROWSER') != '1':
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        (ROOT / 'startup-error.log').write_text(detail, encoding='utf-8')
        print(detail, file=sys.stderr)
        print('See startup-error.log in the application folder.', file=sys.stderr)
        sys.exit(1)
