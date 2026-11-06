# Third-party software

The solver mathematics in `solver/tet10.py`, boundary transfer, geometry pipeline and postprocessing were implemented in this standalone project. Numerical verification compares against scikit-fem; this is not an Abaqus solver wrapper.

- Gmsh 4.15.2: https://gmsh.info/ and https://gitlab.onelab.info/gmsh/gmsh — GNU GPL, with the additional exceptions described in its distribution. Native library is included under `vendor` for this local experiment.
- scikit-fem 12.0.2: https://github.com/kinnala/scikit-fem — BSD-3-Clause. Quadrature data is loaded from the package; package licenses remain with its installed metadata.
- meshio 5.3.5: https://github.com/nschloe/meshio — MIT.
- PyAMG 5.3.0: https://github.com/pyamg/pyamg — MIT.
- NumPy, SciPy: BSD-style licenses in their distributions.
- Plotly.js: https://github.com/plotly/plotly.js — MIT; its embedded source banner is retained in the offline HTML.

See the distributions' license texts before redistributing a combined application. Abaqus is a separate installed proprietary application used only for optional result database export and viewing.
