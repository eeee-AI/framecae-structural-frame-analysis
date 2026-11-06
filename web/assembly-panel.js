(() => {
  if (document.querySelector('#assemblySettings')) return;

  const panel = document.createElement('details');
  panel.id = 'assemblySettings';
  panel.open = true;
  panel.innerHTML = `
    <summary>装配内力：杆件制造长度偏差</summary>
    <p class="help">输入 Δl = L制造 − L设计（m）。Δl&lt;0 表示杆件偏短，装到设计节点间距时被拉长；Δl&gt;0 表示偏长，会受压。长度偏差作为初应变参与整体刚架求解，可与节点荷载、杆件荷载、温差、自重同时叠加。</p>
    <div class="assembly-toolbar actions">
      <button id="addAssemblyDeviation" class="secondary">新增杆件偏差</button>
      <button id="clearAssemblyDeviation" class="secondary">清空偏差</button>
      <span class="help">局部杆端轴力 N&lt;0 为拉力，N&gt;0 为压力。</span>
    </div>
    <div class="table-wrap"><table id="assemblyDeviationTable"><thead><tr><th>杆件</th><th>制造长度偏差 Δl (m)</th><th>初应变 ε₀ = Δl/L</th><th></th></tr></thead><tbody></tbody></table></div>
    <p id="assemblyHint" class="help">请先填写偏差，再点击“从表格计算”。自由端可释放装配应力；两端受约束时会产生装配内力与支座反力。</p>`;
  (document.querySelector('#strengthCheckSettings') || document.querySelector('#genericLocalSettings') || document.querySelector('#localSettings')).insertAdjacentElement('beforebegin', panel);

  let deviations = [];
  const validElementIds = () => new Set((data.elements || []).map(item => Number(item.id)));
  const normalized = rows => (Array.isArray(rows) ? rows : [])
    .map(row => ({element: Number(row.element), deltaLength: Number(row.deltaLength)}))
    .filter(row => Number.isInteger(row.element) && Number.isFinite(row.deltaLength));
  const currentRows = () => Array.from(document.querySelectorAll('#assemblyDeviationTable tbody tr')).map(row => ({
    element: Number(row.querySelector('[data-key="element"]').value),
    deltaLength: Number(row.querySelector('[data-key="deltaLength"]').value),
  })).filter(row => Number.isInteger(row.element) && Number.isFinite(row.deltaLength));
  const elementLength = id => {
    const element = (data.elements || []).find(item => Number(item.id) === Number(id));
    if (!element) return NaN;
    const nodes = new Map((data.nodes || []).map(node => [Number(node.id), node]));
    const start = nodes.get(Number(element.start)); const end = nodes.get(Number(element.end));
    if (!start || !end) return NaN;
    return Math.hypot(Number(end.x) - Number(start.x), Number(end.y) - Number(start.y), Number(end.z) - Number(start.z));
  };
  const render = () => {
    const body = document.querySelector('#assemblyDeviationTable tbody');
    deviations = normalized(deviations).filter(row => validElementIds().has(row.element));
    body.innerHTML = deviations.map((row, index) => {
      const length = elementLength(row.element);
      const strain = Number.isFinite(length) && length > 0 ? row.deltaLength / length : NaN;
      const options = (data.elements || []).map(item => `<option value="${Number(item.id)}" ${Number(item.id) === row.element ? 'selected' : ''}>E${Number(item.id)}</option>`).join('');
      return `<tr data-index="${index}"><td><select data-key="element">${options}</select></td><td><input data-key="deltaLength" type="number" step="any" value="${row.deltaLength}"></td><td>${Number.isFinite(strain) ? strain.toExponential(4) : '—'}</td><td><button class="remove-row" title="删除">×</button></td></tr>`;
    }).join('');
    body.querySelectorAll('input,select').forEach(control => control.onchange = () => { deviations = currentRows(); render(); });
    body.querySelectorAll('.remove-row').forEach(button => button.onclick = () => { deviations.splice(Number(button.closest('tr').dataset.index), 1); render(); });
  };
  const syncFromModel = source => { deviations = normalized(source); render(); };

  const rawPayload = payload;
  payload = () => ({...rawPayload(), assemblyDeviations: normalized(currentRows())});
  const rawLoadDefault = loadDefault;
  loadDefault = async () => { await rawLoadDefault(); syncFromModel(data.assemblyDeviations); };
  const rawImport = importModel;
  importModel = file => {
    const reader = new FileReader();
    reader.onload = () => {
      try { deviations = normalized(JSON.parse(reader.result).assemblyDeviations); } catch (_) { deviations = []; }
      rawImport(file);
      window.setTimeout(render, 30);
    };
    reader.readAsText(file, 'utf-8');
  };
  const rawWriteResults = writeResults;
  writeResults = function () {
    rawWriteResults();
    const entries = result?.summary?.assembly;
    if (!entries?.length) return;
    const text = entries.map(item => {
      const state = item.deltaLength < 0 ? '偏短／装配拉长' : '偏长／装配压缩';
      return `E${item.element}: Δl=${item.deltaLength.toExponential(4)} m，ε₀=${item.installationStrain.toExponential(4)}，${state}，起端 N=${item.startAxialForce.toExponential(4)} N。`;
    }).join('\n');
    document.querySelector('#results').textContent += `\n\n装配内力结果（局部杆端 N<0 为拉力，N>0 为压力）：\n${text}`;
  };
  document.querySelector('#addAssemblyDeviation').onclick = () => {
    const first = (data.elements || [])[0];
    if (!first) return;
    deviations = currentRows(); deviations.push({element: Number(first.id), deltaLength: 0}); render();
  };
  document.querySelector('#clearAssemblyDeviation').onclick = () => { deviations = []; render(); };
  render();
})();
