"""启动 FrameCAE 的本机浏览器可视化界面。"""

import os
import importlib.util
from pathlib import Path
import sys

# Use the project environment when an IDE or command prompt selected a Python
# installation without the required numerical libraries.
if any(importlib.util.find_spec(name) is None for name in ('numpy', 'scipy')):
    project_python = Path(__file__).resolve().parent / '.venv' / 'Scripts' / 'python.exe'
    if project_python.is_file() and Path(sys.executable).resolve() != project_python.resolve():
        os.execv(str(project_python), [str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit('缺少数值计算依赖。请双击项目目录中的“启动FrameCAE.cmd”完成安装并启动。')

# 局部实体收敛分析会反复调用小规模线性代数；限制 OpenBLAS 线程数，避免多次
# 打开本机界面后线程池叠加占用内存。
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("FRAMECAE_PORT", "62183")

from webapp import main


if __name__ == "__main__":
    main()
