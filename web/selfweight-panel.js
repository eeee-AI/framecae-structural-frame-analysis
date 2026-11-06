(() => {
  if (document.querySelector('#selfWeightSettings')) return;
  const schema = schemas.materials;
  if (!schema.fields.some(([key]) => key === 'density')) schema.fields.push(['density', '密度 ρ (kg/m³)']);
  schema.blank.density = 7850;

  const panel = document.createElement('details');
  panel.id = 'selfWeightSettings';
  panel.open = true;
  panel.innerHTML = `
    <summary>构件自重</summary>
    <div class="local-grid">
      <label><input id="selfWeightEnabled" type="checkbox"> 计入构件自重</label>
      <label>gx (m/s²) <input id="gravityX" value="0"></label>
      <label>gy (m/s²) <input id="gravityY" value="0"></label>
      <label>gz (m/s²) <input id="gravityZ" value="-9.81"></label>
    </div>
    <div class="actions"><button id="restoreGravity" class="secondary">恢复竖向重力</button></div>
    <p id="selfWeightHint" class="help">自重按每根杆的 ρA·g 自动形成一致等效节点荷载；材料表可编辑密度。启用或修改后点击“从表格计算”。</p>`;
  (document.querySelector('#strengthCheckSettings') || document.querySelector('#genericLocalSettings') || document.querySelector('#localSettings')).insertAdjacentElement('beforebegin', panel);

  const controls = () => ({
    enabled: document.querySelector('#selfWeightEnabled').checked,
    gx: Number(document.querySelector('#gravityX').value),
    gy: Number(document.querySelector('#gravityY').value),
    gz: Number(document.querySelector('#gravityZ').value),
  });
  const fill = value => {
    const source = value || {};
    document.querySelector('#selfWeightEnabled').checked = Boolean(source.enabled);
    document.querySelector('#gravityX').value = source.gx ?? 0;
    document.querySelector('#gravityY').value = source.gy ?? 0;
    document.querySelector('#gravityZ').value = source.gz ?? -9.81;
  };
  const addDensityDefaults = () => (data.materials || []).forEach(item => {
    if (item.density === undefined || item.density === null || item.density === '') item.density = 7850;
  });
  const rawPayload = payload;
  payload = () => ({...rawPayload(), selfWeight: controls()});
  const rawLoadDefault = loadDefault;
  loadDefault = async () => {
    await rawLoadDefault(); addDensityDefaults(); fill(data.selfWeight); renderTables();
  };
  const rawImport = importModel;
  importModel = file => {
    const reader = new FileReader();
    reader.onload = () => {
      try { fill(JSON.parse(reader.result).selfWeight); } catch (_) { fill(); }
      rawImport(file);
      window.setTimeout(() => { addDensityDefaults(); renderTables(); }, 20);
    };
    reader.readAsText(file, 'utf-8');
  };
  const rawWriteResults = writeResults;
  writeResults = function () {
    rawWriteResults();
    const summary = result?.summary?.selfWeight;
    if (!summary?.enabled) return;
    const weight = summary.totalWeight || [0, 0, 0];
    document.querySelector('#results').textContent += `\n\n构件自重：总质量 ${summary.totalMass.toFixed(2)} kg；重力合力 [${weight.map(value => value.toExponential(4)).join(', ')}] N。`;
  };
  document.querySelector('#restoreGravity').onclick = () => fill({enabled: controls().enabled, gx: 0, gy: 0, gz: -9.81});
  addDensityDefaults();
})();
