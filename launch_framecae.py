"""Install project-local dependencies and launch the local application."""
from pathlib import Path
import os
import subprocess
import sys
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def main():
    os.chdir(ROOT)
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not python.is_file():
        print('Preparing FrameCAE Python environment...', flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    check = subprocess.run([str(python), '-c', 'import framecae.solid_local; import numpy, scipy, cv2, gmsh, skfem, pyamg, meshio'], capture_output=True)
    if check.returncode:
        print('Installing FrameCAE dependencies...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    env = os.environ.copy()
    env.setdefault('FRAMECAE_PORT', '62183')
    address = f"http://127.0.0.1:{int(env['FRAMECAE_PORT'])}"
    # Reuse only an identified FrameCAE server; never stop another application.
    try:
        import json
        local_http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with local_http.open(address + '/api/health', timeout=2) as response:
            health = json.load(response)
        if health.get('application') == 'FrameCAE' and health.get('status') == 'ok' and 'calibratedImageReconstructionV3' in health.get('features',[]) and Path(health.get('project','')).resolve()==ROOT.resolve():
            webbrowser.open(address)
            print('FrameCAE is already running: ' + address, flush=True)
            return
        if health.get('application') == 'FrameCAE':
            # Keep existing windows/processes intact; use another free port for this version.
            import socket
            for port in range(int(env['FRAMECAE_PORT'])+1,int(env['FRAMECAE_PORT'])+21):
                with socket.socket() as probe:
                    try: probe.bind(('127.0.0.1',port))
                    except OSError: continue
                env['FRAMECAE_PORT']=str(port)
                print('Starting updated FrameCAE on port '+str(port),flush=True)
                break
    except (OSError, ValueError):
        pass
    subprocess.run([str(python), str(ROOT / 'app.py')], env=env, check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('FrameCAE startup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
