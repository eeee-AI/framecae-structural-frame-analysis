(() => {
  const editor = document.querySelector('#editor');
  const anchor = document.querySelector('#genericLocalSettings');
  if (!editor || !anchor || document.querySelector('#fullStressSettings')) return;

  const panel = document.createElement('section');
  panel.id = 'fullStressSettings';
  panel.innerHTML = `
    <h2>三维刚架满应力尺寸试算</h2>
    <p class="help">每轮按几何相似关系同步更新 A、Iy、Iz、J、D，重新求解三维刚架。按轴力、双向弯矩、扭矩和剪力估算名义强度，并检查受压杆的 Euler 稳定。计算后右侧可按截面面积显示杆件粗细，并预览隐藏细杆的形态。</p>
    <div class="full-stress-controls">
      <label>允许轴向应力 (MPa)<input id="fsAllowable" type="number" min="0.001" value="235"></label>
      <label>最多迭代次数<input id="fsIterations" type="number" min="1" max="100" value="30"></label>
      <label>最小面积 / 初始面积<input id="fsMinimum" type="number" min="0.000001" max="0.999" step="0.01" value="0.01"></label>
      <label>单轮面积变化上限<input id="fsMove" type="number" min="0.001" max="0.999" step="0.05" value="0.5"></label>
      <label>收敛容差<input id="fsTolerance" type="number" min="0.000001" step="0.001" value="0.001"></label>
      <label>稳定计算长度系数 μ<input id="fsEffectiveLength" type="number" min="0.01" step="0.1" value="1"></label>
    </div>
    <div class="full-stress-actions"><button id="fsOneStep" class="secondary">满应力迭代一步</button><button id="fsRun" class="secondary">自动迭代</button><button id="fsExport" class="secondary" disabled>导出迭代结果</button><button id="fsExportModel" class="secondary" disabled>导出优化模型</button></div>
    <p id="fsMessage" class="help" role="status">先在 01 确认并计算模型，再运行刚架尺寸迭代。</p>
    <div id="fsOutput" hidden>
      <div id="fsSummary"></div>
      <label class="fs-history-label">查看迭代轮次 <select id="fsHistory"></select></label>
      <div class="fs-table-wrap"><table><thead><tr><th>控制利用率排名</th><th>杆件</th><th>最大轴力 (N)</th><th>最大弯矩 (N·m)</th><th>面积 (m²)</th><th>面积/初始</th><th>强度利用率</th><th>稳定利用率</th><th>控制项</th></tr></thead><tbody id="fsRows"></tbody></table></div>
      <p id="fsCandidates" class="help"></p>
      <p class="help">强度按名义梁截面估算，稳定按指定 μ 的 Euler 压杆模型初步校核；不包含焊缝和节点局部应力。极小面积构件未实际删除，位移限值和删杆后的结构稳定性仍需独立检查。</p>
    </div>`;
  anchor.insertAdjacentElement('beforebegin', panel);
  const css = document.createElement('style');
  css.textContent = `#fullStressSettings h2{font-size:19px;margin:3px 0 10px}#fullStressSettings>.help{line-height:1.7}.full-stress-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.full-stress-controls label{font-size:12px}.full-stress-controls input{display:block;width:100%;margin-top:4px;padding:6px;border:1px solid #d9e1ee;border-radius:5px;background:white}.full-stress-actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.fs-history-label{display:flex;align-items:center;gap:10px;margin:12px 0}.fs-history-label select{padding:5px;border:1px solid #d9e1ee;border-radius:5px;background:white}.fs-table-wrap{max-height:340px;overflow:auto}.fs-table-wrap table{width:100%;font-size:12px}.fs-table-wrap th,.fs-table-wrap td{padding:6px;white-space:nowrap}.fs-view-controls{display:flex;align-items:center;gap:9px;flex-wrap:wrap;border-left:1px solid #d8e0ec;padding-left:9px}.fs-view-controls select{min-width:92px}.fs-view-controls input[type=range]{width:86px;min-width:86px;accent-color:#16828d}.fs-view-controls output{min-width:30px;text-align:right}.fs-view-controls small{color:#617489}@media(max-width:650px){.full-stress-controls{grid-template-columns:1fr}}`;
  document.head.append(css);

  const $ = selector => panel.querySelector(selector);
  let latest = null;
  let demonstratedSteps = 0;
  let demonstrationModel = '';
  const number = (value, digits=4) => Number(value).toPrecision(digits);
  const viewControls = document.createElement('span');
  viewControls.className = 'fs-view-controls';
  viewControls.innerHTML = '<label>截面预览 <select id="fsViewMode" aria-label="满应力杆件视图"><option value="original">原始结果</option><option value="sized">优化后粗细</option><option value="retained">隐藏细杆</option></select></label><label id="fsCutoffLabel">隐藏面积比低于 <input id="fsCutoff" type="range" min="1" max="100" value="5" aria-label="隐藏面积比例阈值"><output id="fsCutoffValue">5%</output></label><small id="fsViewCount"></small>';
  document.querySelector('#viewer .toolbar').append(viewControls);
  const viewMode = viewControls.querySelector('#fsViewMode');
  const cutoff = viewControls.querySelector('#fsCutoff');
  const defaultLegend = Array.from(document.querySelector('.legend').children).map(item => item.style.display);
  const previewLegend = document.createElement('span');
  previewLegend.id = 'fsPreviewLegend';
  previewLegend.textContent = '线宽 ∝ 截面直径；灰虚线为原始杆件。';
  previewLegend.hidden = true;
  document.querySelector('.legend').append(previewLegend);
  let latestModelSignature = '';
  const previewActive = () => window.frameCAEActiveModule === 'fullStress' && viewMode.value !== 'original' && latest && result && displayMode === 'global';
  const syncViewControls = () => {
    viewControls.style.display = window.frameCAEActiveModule === 'fullStress' ? 'flex' : 'none';
    viewMode.querySelectorAll('option:not(:first-child)').forEach(option => option.disabled = !latest);
    viewControls.querySelector('#fsCutoffLabel').style.display = viewMode.value === 'retained' ? 'flex' : 'none';
    viewControls.querySelector('#fsCutoffValue').textContent = `${cutoff.value}%`;
    const active = Boolean(previewActive());
    Array.from(document.querySelector('.legend').children).slice(0, defaultLegend.length).forEach((item, index) => {
      item.style.display = active ? 'none' : defaultLegend[index];
    });
    previewLegend.hidden = !active;
    previewLegend.textContent = viewMode.value === 'retained'
      ? `按初始面积的 ${cutoff.value}% 隐藏细杆，仅作形态预览；删杆后尚未重分析。`
      : '线宽随截面直径变化；灰虚线是原始杆件，橙色是缩小的杆件。';
  };
  const baseDraw = draw;
  draw = function () {
    syncViewControls();
    if (!previewActive()) { baseDraw(); return; }
    if (JSON.stringify(payload()) !== latestModelSignature) {
      viewMode.value = 'original';
      $('#fsMessage').textContent = '模型已修改，旧的优化预览已关闭。请重新运行满应力计算。';
      syncViewControls();
      baseDraw();
      return;
    }
    const selected = Number($('#fsHistory').value);
    const step = latest.history[selected] || latest.history.at(-1);
    const rows = new Map(step.members.map(row => [Number(row.id), row]));
    const nodes = new Map(result.nodes.map(node => [Number(node.id), node]));
    const threshold = Number(cutoff.value) / 100;
    const visible = result.elements.filter(element => {
      const row = rows.get(Number(element.id));
      return row && (viewMode.value !== 'retained' || row.areaRatio >= threshold);
    });
    const width = canvas.clientWidth, height = canvas.clientHeight;
    setup();
    ctx.clearRect(0, 0, width, height);
    const factor = Math.max(0, Number(document.querySelector('#scale').value) || 0);
    const points = result.nodes.flatMap(node => [node.coordinate, node.coordinate.map((value, index) => value + factor * node.displacement[index])]);
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    points.forEach(point => point.forEach((value, index) => { low[index] = Math.min(low[index], value); high[index] = Math.max(high[index], value); }));
    const center = low.map((value, index) => (value + high[index]) / 2);
    const span = Math.max(...high.map((value, index) => value - low[index]), 1);
    const pixels = Math.min(width, height) * .56 / span * view.zoom;
    const project = point => {
      const x = point[0] - center[0], y = point[1] - center[1], z = point[2] - center[2];
      const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
      const xr = cy * x - sy * y, yr = sy * x + cy * y, zr = cp * z - sp * yr;
      return {x: width / 2 + xr * pixels, y: height / 2 - zr * pixels, depth: sp * z + cp * yr};
    };
    const ends = element => [project(nodes.get(Number(element.start)).coordinate), project(nodes.get(Number(element.end)).coordinate)];
    const ordered = [...visible].sort((a, b) => {
      const pa = ends(a), pb = ends(b);
      return pa[0].depth + pa[1].depth - pb[0].depth - pb[1].depth;
    });
    if (viewMode.value === 'sized') {
      ctx.setLineDash([5, 5]); ctx.lineWidth = 1.1; ctx.strokeStyle = '#a5b1bd';
      result.elements.forEach(element => {
        const [a, b] = ends(element);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      });
      ctx.setLineDash([]);
    }
    ctx.setLineDash([]);
    const maxArea = Math.max(...step.members.map(row => row.area), 1e-18);
    const connected = new Set();
    ordered.forEach(element => {
      const row = rows.get(Number(element.id)), [a, b] = ends(element);
      connected.add(Number(element.start)); connected.add(Number(element.end));
      ctx.strokeStyle = row.areaRatio < .95 ? '#db8738' : '#16828d';
      ctx.lineWidth = Math.max(1.5, 19 * Math.sqrt(row.area / maxArea));
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      if (document.querySelector('#elementLabels').checked) {
        ctx.fillStyle = '#243c50'; ctx.font = 'bold 12px sans-serif';
        ctx.fillText(`E${element.id}`, (a.x + b.x) / 2 + 4, (a.y + b.y) / 2 - 5);
      }
    });
    ctx.lineCap = 'butt';
    connected.forEach(id => {
      const point = project(nodes.get(id).coordinate);
      ctx.fillStyle = '#fff'; ctx.strokeStyle = '#37566c'; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(point.x, point.y, 3.8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      if (document.querySelector('#nodeLabels').checked) {
        ctx.fillStyle = '#37566c'; ctx.font = '11px sans-serif'; ctx.fillText(`N${id}`, point.x + 6, point.y - 5);
      }
    });
    const hidden = result.elements.length - visible.length;
    const count = `第 ${step.iteration} 轮 · 显示 ${visible.length}/${result.elements.length} 根${hidden ? ` · 隐藏 ${hidden} 根` : ''}`;
    viewControls.querySelector('#fsViewCount').textContent = count;
    ctx.fillStyle = '#324b5e'; ctx.font = '12px sans-serif'; ctx.fillText(count, 12, 20);
    if (viewMode.value === 'retained') {
      ctx.fillStyle = '#8b562a'; ctx.fillText('隐藏仅供预览，结构未执行删杆重分析', 12, 39);
    }
  };
  viewMode.onchange = () => { syncViewControls(); draw(); };
  cutoff.oninput = () => { syncViewControls(); draw(); };
  window.addEventListener('framecae-module-change', () => requestAnimationFrame(() => { syncViewControls(); draw(); }));
  syncViewControls();
  const options = iterations => ({
    allowableStress: Number($('#fsAllowable').value) * 1e6,
    maxIterations: iterations,
    minAreaFraction: Number($('#fsMinimum').value),
    moveLimit: Number($('#fsMove').value),
    tolerance: Number($('#fsTolerance').value),
    effectiveLengthFactor: Number($('#fsEffectiveLength').value),
  });
  const showIteration = index => {
    const item = latest.history[index];
    $('#fsSummary').textContent = `第 ${item.iteration} 轮 · 体积 ${number(item.volume, 7)} m³ · 强度最大 ${(item.maxStrengthUtilization * 100).toFixed(1)}% · 稳定最大 ${(item.maxStabilityUtilization * 100).toFixed(1)}% · 最大位移 ${number(item.maxDisplacement, 5)} m`;
    $('#fsRows').replaceChildren(...item.members.map(row => {
      const tr = document.createElement('tr');
      [row.rank, row.id, number(row.maxAxialForce, 6), number(row.maxBendingMoment, 6), number(row.area, 6),
        `${(row.areaRatio * 100).toFixed(2)}%`, `${(row.strengthUtilization * 100).toFixed(1)}%`,
        `${(row.stabilityUtilization * 100).toFixed(1)}%`, row.governing]
        .forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
      return tr;
    }));
  };
  $('#fsHistory').onchange = () => { showIteration(Number($('#fsHistory').value)); draw(); };
  const run = async (iterations, overrides={}) => {
    if (!window.frameCAEHasConfirmedModel?.()) {
      $('#fsMessage').textContent = '请先在 01 确认模型并完成整体计算。';
      return false;
    }
    const model = payload();
    const request = {model, settings: {...options(iterations), ...overrides}};
    const signature = JSON.stringify(request);
    $('#fsRun').disabled = $('#fsOneStep').disabled = true;
    $('#fsMessage').textContent = '正在逐轮组装三维刚架刚度矩阵并重分析…';
    try {
      const response = await fetch('/api/full-stress', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: signature,
      });
      if (response.status === 404)
        throw Error('当前本地服务仍是旧版本。请先导出模型，再关闭服务窗口并重新双击“启动FrameCAE.cmd”。');
      const answer = await response.json();
      if (!response.ok) throw Error(answer.error || '满应力计算失败。');
      if (!String(answer.method || '').startsWith('space_frame_fixed_volume_'))
        throw Error('当前标签页连接的仍是桁架版服务。请重新打开新版 FrameCAE 页面。');
      if (signature !== JSON.stringify({model: payload(), settings: {...options(iterations), ...overrides}}))
        throw Error('计算期间模型或参数已修改，请重新运行。');
      latest = answer;
      latestModelSignature = JSON.stringify(model);
      $('#fsHistory').replaceChildren(...answer.history.map(item => {
        const option = document.createElement('option');
        option.value = item.iteration;
        option.textContent = `第 ${item.iteration} 轮`;
        return option;
      }));
      $('#fsHistory').value = String(answer.history.length - 1);
      showIteration(answer.history.length - 1);
      viewMode.value = 'sized';
      syncViewControls();
      draw();
      $('#fsCandidates').textContent = answer.candidateRemovalIds.length
        ? `极小面积构件：${answer.candidateRemovalIds.map(id => `E${id}`).join('、')}。未实际删除。`
        : '当前没有面积小于初始面积 5% 的构件。';
      $('#fsOutput').hidden = false;
      $('#fsExport').disabled = false;
      $('#fsExportModel').disabled = !answer.optimizedModel;
      $('#fsMessage').textContent = `完成 ${answer.iterations} 轮重分析${answer.converged ? '，面积变化已收敛' : '，达到本次迭代上限'}。体积相对误差 ${Math.abs(answer.finalVolume / answer.initialVolume - 1).toExponential(2)}。`;
      return true;
    } catch (error) {
      $('#fsMessage').textContent = error.message;
      return false;
    } finally {
      $('#fsRun').disabled = $('#fsOneStep').disabled = false;
    }
  };
  $('#fsOneStep').onclick = async () => {
    const modelSignature = JSON.stringify(payload());
    if (modelSignature !== demonstrationModel) {
      demonstrationModel = modelSignature;
      demonstratedSteps = 0;
    }
    const next = Math.min(demonstratedSteps + 1, 100);
    if (await run(next)) demonstratedSteps = next;
  };
  $('#fsRun').onclick = async () => {
    const iterations = Number($('#fsIterations').value);
    if (await run(iterations)) {
      demonstrationModel = JSON.stringify(payload());
      demonstratedSteps = latest.iterations;
    }
  };
  $('#fsExport').onclick = () => {
    if (!latest) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(latest, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'framecae_full_stress.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };
  $('#fsExportModel').onclick = () => {
    if (!latest?.optimizedModel) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(latest.optimizedModel, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'framecae_optimized_frame_model.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };
})();
