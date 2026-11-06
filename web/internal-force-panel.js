(() => {
  if (document.querySelector('#internalForceSettings')) return;
  const editor = document.querySelector('#editor');
  const viewer = document.querySelector('#viewer');
  if (!editor || !viewer) return;

  const style = document.createElement('style');
  style.textContent = `
    #internalForceSettings{border:0;padding:0}.force-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0}.force-actions button{min-height:42px}.force-actions button.active{background:#125eaf;box-shadow:inset 0 0 0 2px #072f5a}.force-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.force-controls label{display:flex;align-items:center;gap:6px;font-size:13px}.force-controls select,.force-controls input{min-width:0;border:1px solid #cfddeb;border-radius:5px;padding:6px;background:#fff}.force-summary{padding:10px;border:1px solid #d6e2ef;border-radius:8px;background:#f8fbff;color:#425873;font-size:13px;line-height:1.6}.force-key{margin:9px 0 0;padding:8px 10px;border-left:3px solid #2f75c5;background:#f5f9fd;color:#526983;font-size:12px;line-height:1.55}.force-overlay-label{font:12px "Microsoft YaHei UI",sans-serif;fill:#183b60;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}@media(max-width:640px){.force-actions,.force-controls{grid-template-columns:1fr}}
  `;
  document.head.append(style);

  const panel = document.createElement('section');
  panel.id = 'internalForceSettings';
  panel.innerHTML = `
    <h3 style="margin:0 0 6px">杆件内力图：三维后处理</h3>
    <p class="help">直接读取已确认结构的整体梁单元沿程内力；右侧三维图定位杆件，沿程曲线显示选中杆件的实际截面数值。</p>
    <div class="force-actions">
      <button type="button" data-force-mode="bending">弯矩图<br><small>My / Mz</small></button>
      <button type="button" data-force-mode="torsion" class="secondary">扭矩图<br><small>T</small></button>
      <button type="button" data-force-mode="axial" class="secondary">拉压图<br><small>N</small></button>
    </div>
    <div class="force-controls">
      <label>选中杆件 <select id="forceSelectedElement"></select></label>
      <label>图形放大 <input id="forceScale" type="range" min="0.25" max="3" step="0.05" value="1"></label>
      <label><input id="forceValueLabels" type="checkbox" checked> 显示极值标签</label>
      <button id="forceHide" type="button" class="secondary">隐藏内力图</button>
    </div>
    <div id="forceSummary" class="force-summary">请先在 01 中确认结构并完成整体求解。</div>
    <p id="forceConvention" class="force-key"></p>`;
  editor.append(panel);

  const memberToolbar = document.querySelector('.member-toolbar');
  const memberCanvas = document.querySelector('#memberDiagram');
  if (memberToolbar) memberToolbar.style.display = 'none';
  if (memberCanvas) memberCanvas.style.display = 'none';

  const state = {active: false, mode: 'bending', selected: null};
  window.frameCAEForceView = state;
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const vector = (point, direction, amount) => point.map((value, index) => value + direction[index] * amount);
  const lerp = (first, second, ratio) => first.map((value, index) => value + (second[index] - value) * ratio);
  const magnitude = value => Math.abs(number(value));
  const localAxes = element => element.localAxes || [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const signedColor = (value, positive, negative) => number(value) >= 0 ? positive : negative;
  const stationValue = (station, component) => number(station.forces?.[component]);
  const displayedComponents = () => state.mode === 'bending' ? [4, 5] : state.mode === 'torsion' ? [3] : [0];
  const modeText = () => ({bending: '弯矩图', torsion: '扭矩图', axial: '拉压图'})[state.mode];
  const conventionText = () => ({
    bending: '弯矩图：My 为绕局部 +y 的内力矩，绘制在局部 z 偏置图面；Mz 为绕局部 +z 的内力矩，绘制在局部 y 偏置图面。正负值按绕局部 +y、+z 的右手定则绘于杆轴两侧。',
    torsion: '扭矩图：沿杆绘制平面色带，离杆轴越远表示 |T| 越大。T > 0 按绕局部 +x 的右手定则，绘于局部 +y 侧（绿色）；T < 0 绘于 −y 侧（橙色）。图面方向仅用于显示，不表示杆件弯曲方向。',
    axial: '拉压图：N > 0 为压力，蓝色；N < 0 为拉力，红色。图形位于局部 y 偏置方向，正负值分居杆轴两侧。',
  })[state.mode];
  const forceScale = () => Math.max(.25, number(document.querySelector('#forceScale')?.value) || 1);

  const setMode = mode => {
    // “隐藏”后再次点击任一模式，应立即恢复相应的三维内力图。
    state.active = true;
    state.mode = mode;
    panel.querySelectorAll('[data-force-mode]').forEach(button => {
      const selected = button.dataset.forceMode === mode;
      button.classList.toggle('active', selected); button.classList.toggle('secondary', !selected);
    });
    document.querySelector('#forceConvention').textContent = conventionText();
    updateSummary(); draw();
  };
  const buildSelector = () => {
    const select = document.querySelector('#forceSelectedElement');
    const selected = state.selected ?? select.value;
    select.innerHTML = (result?.elements || []).map(element => `<option value="${element.id}">E${element.id}</option>`).join('');
    if ([...select.options].some(option => option.value === String(selected))) select.value = String(selected);
    else if (select.options.length) { const candidate=result.elements.reduce((best,e)=>{const peak=(e.stations||[]).reduce((m,s)=>Math.max(m,...displayedComponents().map(c=>magnitude(stationValue(s,c)))),0);return !best||peak>best.peak?{id:e.id,peak}:best;},null);select.value=String(candidate.id);state.selected=candidate.id; }
  };
  const extrema = () => {
    const components = displayedComponents();
    const all = (result?.elements || []).flatMap(element => (element.stations || []).flatMap(station => components.map(component => ({element, station, component, value: stationValue(station, component)}))));
    const positive = all.filter(item => item.value >= 0).sort((a, b) => b.value - a.value)[0];
    const negative = all.filter(item => item.value <= 0).sort((a, b) => a.value - b.value)[0];
    return {all, positive, negative, maximum: all.reduce((m,item) => Math.max(m,magnitude(item.value)),1e-12)};
  };
  const textForce = value => `${(number(value)/1000).toFixed(3)} ${state.mode === 'axial' ? 'kN' : 'kN·m'}`;
  const componentName = component => ({0: 'N', 3: 'T', 4: 'My', 5: 'Mz'})[component];
  const updateSummary = () => {
    const summary = document.querySelector('#forceSummary');
    if (!result?.elements?.length) { summary.textContent = '请先在 01 中确认结构并完成整体求解。'; return; }
    buildSelector();
    const data = extrema(), selected = result.elements.find(element => element.id === Number(document.querySelector('#forceSelectedElement').value));
    const endpoint = item => item ? `E${item.element.id}，x=${number(item.station.position).toFixed(3)} m，${componentName(item.component)}=${textForce(item.value)}` : '无';
    const selectedItems = (selected?.stations || []).flatMap(station => displayedComponents().map(component => ({station, component, value: stationValue(station, component)})));
    const selectedPeak = selectedItems.sort((first, second) => magnitude(second.value) - magnitude(first.value))[0];
    summary.innerHTML = `<b>${modeText()}｜全结构极值</b><br>最大正值：${endpoint(data.positive)}<br>最大负值：${endpoint(data.negative)}<br><span class="help">选中 E${selected?.id ?? '—'} 的最大绝对值：${selectedPeak ? `${componentName(selectedPeak.component)}=${textForce(selectedPeak.value)}，x=${number(selectedPeak.station.position).toFixed(3)} m` : '—'}</span>`;
  };

  const sceneProjection = () => {
    const width = canvas.clientWidth, height = canvas.clientHeight, factor = Math.max(0, number(document.querySelector('#scale')?.value));
    const nodes = result.nodes, nodeMap = Object.fromEntries(nodes.map(node => [node.id, node]));
    const allPoints = nodes.flatMap(node => [node.coordinate, node.coordinate.map((value, index) => value + factor * number(node.displacement[index]))]);
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    allPoints.forEach(point => point.forEach((value, index) => { low[index] = Math.min(low[index], value); high[index] = Math.max(high[index], value); }));
    const center = low.map((value, index) => (value + high[index]) / 2), span = Math.max(...high.map((value, index) => value - low[index]), 1e-9);
    const pixels = Math.min(width, height) * .56 / span * view.zoom;
    const project = point => {
      const x = point[0] - center[0], y = point[1] - center[1], z = point[2] - center[2];
      const p = window.FrameCAEModelView.projectOffset([x,y,z],view);
      return {x: width / 2 + p.x * pixels, y: height / 2 + p.y * pixels, depth: p.depth};
    };
    const deformedPoint = node => node.coordinate.map((value, index) => value + factor * number(node.displacement[index]));
    return {project, nodeMap, deformedPoint, pixels};
  };
  const polygonBand = (stations, component, direction, offset, maximum, projection, positive, negative, splitAtZero = false) => {
    const drawSegment = (firstPosition, firstValue, secondPosition, secondValue) => {
      const average = (firstValue + secondValue) / 2;
      const firstBase = projection.base(firstPosition), secondBase = projection.base(secondPosition);
      const firstTop = vector(firstBase, direction, offset * firstValue / maximum), secondTop = vector(secondBase, direction, offset * secondValue / maximum);
      const points = [firstBase, secondBase, secondTop, firstTop].map(projection.project);
      ctx.globalAlpha = .72; ctx.fillStyle = signedColor(average, positive, negative); ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y); points.slice(1).forEach(point => ctx.lineTo(point.x, point.y)); ctx.closePath(); ctx.fill();
      ctx.globalAlpha = .95; ctx.strokeStyle = signedColor(average, positive, negative); ctx.lineWidth = 1.1; ctx.stroke();
    };
    for (let index = 0; index < stations.length - 1; index++) {
      const first = stations[index], second = stations[index + 1];
      const firstValue = stationValue(first, component), secondValue = stationValue(second, component);
      if (splitAtZero && firstValue * secondValue < 0) {
        const zeroPosition = first.position + (second.position - first.position) * firstValue / (firstValue - secondValue);
        drawSegment(first.position, firstValue, zeroPosition, 0);
        drawSegment(zeroPosition, 0, second.position, secondValue);
      } else drawSegment(first.position, firstValue, second.position, secondValue);
    }
  };
  const drawForceOverlay = (sharedProjection) => {
    if (!state.active || !result?.elements?.length || displayMode === 'local') return;
    const all = extrema(); if (!all.all.length) return;
    const projection = sharedProjection || sceneProjection();
    const offset = Math.max(12 / projection.pixels, .025) * forceScale();
    const items = [...result.elements].sort((first, second) => {
      const firstNode = projection.nodeMap[first.start], secondNode = projection.nodeMap[first.end], thirdNode = projection.nodeMap[second.start], fourthNode = projection.nodeMap[second.end];
      return projection.project(projection.deformedPoint(firstNode)).depth + projection.project(projection.deformedPoint(secondNode)).depth - projection.project(projection.deformedPoint(thirdNode)).depth - projection.project(projection.deformedPoint(fourthNode)).depth;
    });
    items.forEach(element => {
      const start = projection.deformedPoint(projection.nodeMap[element.start]), end = projection.deformedPoint(projection.nodeMap[element.end]);
      const length = Math.max(...(element.stations || []).map(station => number(station.position)), 1e-12);
      const local = localAxes(element), stations = element.stations || [];
      const data = {...projection, base: position => lerp(start, end, number(position) / length)};
      if (state.mode === 'axial') polygonBand(stations, 0, local[1], offset, all.maximum, data, '#176ec4', '#df3e45');
      if (state.mode === 'bending') {
        polygonBand(stations, 4, local[2], offset, all.maximum, data, '#a448bd', '#a448bd');
        polygonBand(stations, 5, local[1], offset * 1.15, all.maximum, data, '#139dc0', '#139dc0');
      }
      if (state.mode === 'torsion') polygonBand(stations, 3, local[1], offset, all.maximum, data, '#139d69', '#e07b25', true);
      if (Number(document.querySelector('#forceValueLabels').checked) && element.id === Number(document.querySelector('#forceSelectedElement').value)) {
        const peak = stations.flatMap(station => displayedComponents().map(component => ({station, component, value: stationValue(station, component)}))).sort((first, second) => magnitude(second.value) - magnitude(first.value))[0];
        if (peak) { const point = data.project(data.base(peak.station.position)); ctx.fillStyle = '#173c62'; ctx.font = '12px "Microsoft YaHei UI"'; ctx.fillText(`E${element.id} ${componentName(peak.component)}=${textForce(peak.value)}`, point.x + 7, point.y - 7); }
      }
    });
    ctx.globalAlpha = 1;
    document.querySelector('#legendText').textContent = state.mode === 'axial' ? '拉压图：蓝色压力 N+，红色拉力 N−' : state.mode === 'torsion' ? '扭矩图：绿色 T+ 位于局部 +y 侧，橙色 T− 位于 −y 侧；色带高度表示 |T|' : '弯矩图：紫色 My，青色 Mz；正负值位于杆轴两侧';
    // The common workspace heading identifies the mode without covering the drawing.
  };
  window.frameCAEDrawForceOverlay = drawForceOverlay;
  const baseDraw = draw;
  draw = function () { baseDraw(); drawForceOverlay(); };

  window.frameCAEForceDiagramActive = active => {
    state.active = Boolean(active);
    document.querySelector('#results').style.display = state.active ? 'none' : 'block';
    document.querySelector('#convergence').style.display = state.active ? 'none' : 'block';
    viewer.style.gridTemplateRows = state.active ? 'auto minmax(620px,1fr) auto' : 'auto minmax(430px,1fr) auto minmax(170px,.42fr) 150px';
    if (state.active) { displayMode = 'global'; updateSummary(); }
    draw();
  };
  window.frameCAERefreshInternalForce = () => { buildSelector(); updateSummary(); document.querySelector('#forceConvention').textContent = conventionText(); draw(); };
  panel.querySelectorAll('[data-force-mode]').forEach(button => button.onclick = () => setMode(button.dataset.forceMode));
  document.querySelector('#forceSelectedElement').onchange = event => { state.selected = Number(event.target.value); updateSummary(); draw(); };
  document.querySelector('#forceScale').oninput = () => draw();
  document.querySelector('#forceValueLabels').onchange = () => draw();
  document.querySelector('#forceHide').onclick = () => { state.active = false; panel.querySelectorAll('[data-force-mode]').forEach(button => button.classList.remove('active')); draw(); };
  setMode('bending');
})();
