# FrameCAE: structural frame analysis and local finite elements

FrameCAE is a local web application for structural frame analysis. It combines a global space-frame beam calculation with cut-section force recovery and a local curved Tet10 finite-element workflow for tubular joints. The interface also supports model import, image-assisted reconstruction, and strength inspection.

**Keywords:** structural frame analysis, finite element analysis, FEA, space frame, tubular joint, Tet10, Gmsh, Python, Abaqus comparison.

## Run from source

On Windows, install Python 3.12 and run:

```powershell
python launch_framecae.py
```

The launcher creates a project-local `.venv`, installs `requirements.txt`, and opens the local web application. Package versions are pinned in `requirements.txt`. The original portable distribution uses a bundled `runtime` and `启动FrameCAE.cmd`; those files are not part of this source repository.

## Repository contents

- `framecae/`, `web/`, and the root Python files: application and solver source.
- `六个算例/`, `examples/`, `03参数_可选/`, and selected `02_模型输入/` JSON/CSV files: lightweight examples and inputs.
- `README_full_distribution.md`: documentation for the complete local distribution.

This repository is a **source edition** of the integrated `FrameCAE` directory in `曹馨月更新的`. The original folder also contains a portable Python runtime, third-party native binaries, Abaqus result databases, large model inputs, saved calculations, and a 4.8 GB ZIP archive. Those files total roughly 15 GB and are excluded from this GitHub edition. Archived jobs and some comparison inputs require the original complete distribution; examples here should be rerun to generate new results.

The integrated `FrameCAE` version is used here; the sibling `01_网页程序` in the original folder is an earlier, overlapping version.

## Scope of validation

See `README_full_distribution.md` for the original validation notes. Historical result files do not by themselves establish mesh convergence, truncation-distance convergence, or independent Abaqus agreement. This source edition has not been independently revalidated after removing the archived data and portable runtime.

## Third-party software

Dependencies and their licenses are described in `THIRD_PARTY_solid_solver.md`. This repository does not declare a license for the original project code; reuse beyond GitHub's default viewing and forking permissions needs permission from the rights holder.
