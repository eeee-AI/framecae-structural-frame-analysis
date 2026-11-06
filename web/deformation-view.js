/* Module 01 only: polynomial centreline -> equivalent/error-controlled Bezier paths. */
(() => {
  const previousDraw = draw, geometry = window.FrameCAEBeamCurve;
  const number = v => Number.isFinite(Number(v)) ? Number(v) : 0;
  const moved = (node, scale) => node.coordinate.map((v, i) => v + scale * node.displacement[i]);
  function markers(project, span, scale, byId) {
    if (!document.querySelector('#boundaryMarkers')?.checked) return;
    // Use the model that produced result, never the currently edited draft.
    const source = result.solvedModel || {};
    (source.loads || []).forEach(load => {
      const node = byId[load.node]; if (!node) return;
      const point = moved(node, scale), end = project(point);
      if (Math.hypot(number(load.mx), number(load.my), number(load.mz)) > 1e-12) {
        ctx.fillStyle = '#b62336'; ctx.font = 'bold 15px sans-serif'; ctx.fillText('↻ M', end.x+8, end.y+16);
      }
    });
    (source.constraints || []).forEach(constraint => {
      const node = byId[constraint.node]; if (!node) return;
      const fixed = ['ux', 'uy', 'uz', 'rx', 'ry', 'rz'].filter(key => constraint[key] !== null && constraint[key] !== undefined && constraint[key] !== '');
      if (!fixed.length) return;
      const p = project(moved(node, scale));
      ctx.fillStyle = ctx.strokeStyle = '#1768b3'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(p.x-10, p.y+10); ctx.lineTo(p.x+10, p.y+10); ctx.lineTo(p.x, p.y); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.moveTo(p.x-13, p.y+13); ctx.lineTo(p.x+13, p.y+13); ctx.stroke();
      ctx.fillStyle = '#11548f'; ctx.font = '11px sans-serif'; ctx.fillText(fixed.length === 6 ? '固定' : '约束', p.x+8, p.y+21);
    });
  }
  draw = function () {
    if (!['global','forces'].includes(window.frameCAEActiveModule) || displayMode !== 'global') return previousDraw();
    setup();
    const width = canvas.clientWidth, height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);
    if (!result) return;
    if (!geometry || !result.elements.every(e => e.deformationCurve?.version === 1 && e.deformationCurve.segments.length)) {
      ctx.fillStyle = '#b42330'; ctx.font = '14px sans-serif';
      ctx.fillText('结果缺少连续位移函数，请重新确认结构并计算。', 12, 24); return;
    }
    const scale = Math.max(0, number(document.querySelector('#scale').value)), metric = document.querySelector('#metric').value;
    const byId = Object.fromEntries(result.nodes.map(node => [node.id, node]));
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    const include = point => point.forEach((v, i) => { low[i] = Math.min(low[i], v); high[i] = Math.max(high[i], v); });
    result.nodes.forEach(node => { include(node.coordinate); include(moved(node, scale)); });
    const members = result.elements.map(element => ({element,
      segments: element.deformationCurve.segments.map(segment => ({segment, coefficients: geometry.movedCoefficients(segment, scale)}))}));
    members.forEach(member => member.segments.forEach(part => geometry.hull(part.coefficients).forEach(include)));
    const center = low.map((v, i) => (v+high[i])/2), span = Math.max(...high.map((v, i) => v-low[i]), 1e-9);
    const pixels = Math.min(width, height)*.56/span*view.zoom;
    const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    const project = point => {
      const p = window.FrameCAEModelView.projectOffset(point.map((v,i)=>v-center[i]),view);
      return {x: width/2+p.x*pixels, y: height/2+p.y*pixels, depth: p.depth};
    };
    const memberValue = e => metric === 'axial' ? e.maxAxialForce : metric === 'bending' ? e.maxBendingMoment : e.maxNominalStress;
    const peak = result.summary.deformation.curvePeak;
    const maximum = Math.max(1e-18, metric === 'displacement' ? peak.magnitude : result.elements.reduce((m,e)=>Math.max(m,memberValue(e)),0));
    const color = ratio => `hsl(${260-260*Math.min(1, Math.max(0, ratio))},88%,48%)`;
    members.sort((a, b) => project(geometry.value(a.segments[0].coefficients, .5)).depth-project(geometry.value(b.segments[0].coefficients, .5)).depth);
    ctx.setLineDash([6, 5]); ctx.lineWidth = 1.2; ctx.strokeStyle = '#8996a7';
    result.elements.forEach(e => {
      const a = project(byId[e.start].coordinate), b = project(byId[e.end].coordinate);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    ctx.setLineDash([]); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const stats = {curveCount: 0, maxErrorPixels: 0, limitReached: false, tolerance: .5};
    members.forEach(({element, segments}) => {
      segments.forEach(({segment, coefficients}) => {
        const pieces = geometry.tessellate(coefficients, project, {tolerance: stats.tolerance,
          colorRatio: metric === 'displacement' ? t => Math.hypot(...geometry.value(segment.displacementCoefficients, t))/maximum : undefined});
        pieces.forEach(piece => {
          const p = piece.controls.map(project);
          ctx.lineWidth = 3; ctx.strokeStyle = color(metric === 'displacement' ? piece.colorRatio : memberValue(element)/maximum);
          ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y);
          ctx.bezierCurveTo(p[1].x, p[1].y, p[2].x, p[2].y, p[3].x, p[3].y); ctx.stroke();
          stats.curveCount++; stats.maxErrorPixels = Math.max(stats.maxErrorPixels, piece.errorPixels);
          stats.limitReached ||= piece.limitReached;
        });
      });
      if (document.querySelector('#elementLabels').checked) {
        const x = element.deformationCurve.length/2;
        const part = segments.find(p => x <= p.segment.x1);
        const p = project(geometry.value(part.coefficients, (x-part.segment.x0)/(part.segment.x1-part.segment.x0)));
        ctx.fillStyle = '#253347'; ctx.font = '12px sans-serif'; ctx.fillText('E'+element.id, p.x+4, p.y-4);
      }
    });
    window.frameCAECurveRenderStats = stats;
    result.nodes.forEach(node => {
      const p = project(moved(node, scale));
      ctx.fillStyle = metric === 'displacement' ? color(node.magnitude/maximum) : '#dbe5f0';
      ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = '#172033'; ctx.lineWidth = 1; ctx.stroke();
      if (document.querySelector('#nodeLabels').checked) {
        ctx.fillStyle = '#172033'; ctx.font = '12px sans-serif'; ctx.fillText('N'+node.id, p.x+6, p.y-6);
      }
    });
    window.frameCAEDrawForceOverlay?.({project,nodeMap:byId,deformedPoint:n=>moved(n,scale),pixels});
    markers(project, span, scale, byId);
    if(document.querySelector('#boundaryMarkers')?.checked) {
      const curves=new Map(members.map(m=>[Number(m.element.id),m]));
      const object=p=>({x:p[0],y:p[1],z:p[2]});
      window.FrameCAEModelView.drawModelLoads(ctx,result.solvedModel,p=>project([p.x,p.y,p.z]),width,height,{legend:false,
        nodePoint:(f,p)=>byId[f.id]?object(moved(byId[f.id],scale)):p,
        memberPoint:(q,t,p)=>{const m=curves.get(q.id);if(!m)return p;const x=t*m.element.deformationCurve.length,part=m.segments.find(s=>x<=s.segment.x1)||m.segments.at(-1);return object(geometry.value(part.coefficients,(x-part.segment.x0)/(part.segment.x1-part.segment.x0)));}
      });
    }
    ctx.fillStyle = '#53657d'; ctx.font = '12px sans-serif';
    // Result description and magnification are shown outside the plot.
    if (stats.limitReached) { ctx.fillStyle = '#b42330'; ctx.fillText('警告：当前缩放下达到细分上限，未满足 0.5 像素绘制容限。', 12, height-12); }
    const labels = {displacement: '位移：低 → 高', axial: '轴力：低 → 高', bending: '弯矩：低 → 高', stress: '名义应力：低 → 高'};
    document.querySelector('#legendText').textContent = `${labels[metric]}；连续函数数值最大位移 ${(peak.magnitude*1000).toPrecision(5)} mm（E${peak.element}，x=${peak.position.toPrecision(4)} m，未放大）`;
  };
  const previousWrite = writeResults;
  writeResults = function () {
    previousWrite();
    const peak = result?.summary?.deformation?.curvePeak; if (!peak) return;
    document.querySelector('#results').textContent += `\n\n01 梁位移函数：节点平移＋转角 Hermite 项＋杆上荷载特解。\n连续函数数值最大 |u| = ${peak.magnitude.toExponential(6)} m，E${peak.element}，x=${peak.position.toExponential(6)} m。\n峰值来自各分段端点及 |u|² 的驻点数值计算，不是显示采样最大值；节点最大位移仍单独统计。\n三次段采用等价贝塞尔曲线；四次段按 0.5 CSS 像素误差自适应绘制。\n适用范围：线弹性、小位移、等截面梁；不含横向剪切变形和整体几何非线性。\n03 截断面已共用同一位移函数及其导数；局部加载支持范围见 03 提示。`;
  };
  // Older inline code captured the previous draw object for these listeners.
  ['scale', 'metric', 'nodeLabels', 'elementLabels'].forEach(id =>
    document.getElementById(id)?.addEventListener('input', () => draw()));
  new ResizeObserver(() => { if (window.frameCAEActiveModule === 'global') draw(); }).observe(canvas);
})();

