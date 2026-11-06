/* Pure polynomial/Bezier geometry. Used by module 01 and the Node regression tests. */
(function (root) {
  'use strict';
  const add = (a, b) => a.map((v, i) => v + b[i]);
  const times = (a, s) => a.map(v => v * s);
  const value = (coefficients, t) => coefficients.reduceRight((v, c) => add(times(v, t), c), [0, 0, 0]);
  const derivative = (coefficients, t) => value(coefficients.slice(1).map((c, i) => times(c, i + 1)), t);
  const movedCoefficients = (segment, scale) => segment.coordinateCoefficients.map((c, i) => add(c, times(segment.displacementCoefficients[i], scale)));
  // Degree-4 Bernstein control hull encloses the entire polynomial, including
  // quartic interior bulges even if every nodal displacement is zero.
  function hull(c) {
    return [
      c[0], add(c[0], times(c[1], .25)),
      add(add(c[0], times(c[1], .5)), times(c[2], 1/6)),
      add(add(add(c[0], times(c[1], .75)), times(c[2], .5)), times(c[3], .25)),
      value(c, 1),
    ];
  }
  function controls(c, a, b) {
    const start = value(c, a), end = value(c, b), h = (b-a)/3;
    return [start, add(start, times(derivative(c, a), h)), add(end, times(derivative(c, b), -h)), end];
  }
  function tessellate(c, project, options = {}) {
    const tolerance = options.tolerance ?? .5, maxDepth = options.maxDepth ?? 14;
    if (!(tolerance > 0 && Number.isFinite(tolerance))) throw Error('绘制误差容限必须为有限正数。');
    const zero = project([0, 0, 0]), fourth = project(c[4]);
    const quarticScreenNorm = Math.hypot(fourth.x-zero.x, fourth.y-zero.y);
    const pieces = [];
    function split(a, b, depth) {
      // Quartic minus endpoint-Hermite cubic = c4*(t-a)^2*(t-b)^2.
      // For this affine projection its maximum Euclidean screen error is exact:
      const errorPixels = quarticScreenNorm * (b-a)**4 / 16;
      const ratios = options.colorRatio ? [0, .25, .5, .75, 1].map(t => options.colorRatio(a+(b-a)*t)) : [0];
      const colorSplit = Math.max(...ratios)-Math.min(...ratios) > 1/32;
      if ((errorPixels > tolerance || colorSplit) && depth < maxDepth) {
        const middle = (a+b)/2; split(a, middle, depth+1); split(middle, b, depth+1);
      } else {
        pieces.push({t0: a, t1: b, controls: controls(c, a, b), errorPixels,
          limitReached: errorPixels > tolerance, colorRatio: options.colorRatio ? options.colorRatio((a+b)/2) : 0});
      }
    }
    split(0, 1, 0);
    return pieces;
  }
  const api = {value, derivative, movedCoefficients, hull, controls, tessellate};
  root.FrameCAEBeamCurve = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

