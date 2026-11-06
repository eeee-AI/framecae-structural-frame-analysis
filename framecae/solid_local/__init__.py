"""Independent curved Tet10 backend; optional dependencies are project-local."""
from pathlib import Path
import sys

_vendor=Path(__file__).resolve().parents[2]/'vendor'/'solid_local'
if sys.version_info[:2]==(3,12) and _vendor.is_dir() and str(_vendor) not in sys.path:sys.path.insert(0,str(_vendor))
