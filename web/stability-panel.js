(() => {
  const editor = document.querySelector('#editor');
  const anchor = document.querySelector('#genericLocalSettings') || document.querySelector('#localSettings');
  if (!editor || !anchor || document.querySelector('#stabilityCheckSettings')) return;

  const style = document.createElement('style');
  style.textContent = `
    .stability-cards{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;margin:12px 0}.stability-card{border:1px solid #d9e3ef;border-radius:9px;padding:12px;background:#fbfdff}.stability-card b{display:block;color:#1b4d82;font-size:12px;margin-bottom:5px}.stability-card strong{font-size:20px;color:#132e50}.stability-table td,.stability-table th{white-space:nowrap}.stability-status{font-weight:700}.stability-good{color:#16803d}.stability-warn{color:#b86b00}.stability-fail{color:#c52d37}@media(max-width:850px){.stability-cards{grid-template-columns:repeat(2,minmax(140px,1fr))}}
  `;
  document.head.append(style);

  const panel = document.createElement('details');
  panel.id = 'stabilityCheckSettings';
  panel.open = true;
  panel.innerHTML = `
    <summary>构件稳定校核：Euler 压杆</summary>
    <p class="help">基于整体刚架求解后的沿杆轴力，仅对存在压力的杆件计算 Euler 临界力。局部轴力 N&gt;0 为压力，N&lt;0 为拉力；受拉杆不参与压杆稳定校核。</p>
    <div class="local-grid">
      <label>默认有效长度系数 μy <input id="stabilityDefaultMuY" type="number" min="0.01" step="0.01" value="1.00"></label>
      <label>默认有效长度系数 μz <input id="stabilityDefaultMuZ" type="number" min="0.01" step="0.01" value="1.00"></label>
      <label><input id="stabilityShowTension" type="checkbox"> 结果表显示受拉／零轴力杆</label>
    </div>
    <p class="help">推荐值：两端铰支 μ=1.0；一端固定一端铰支 μ=0.7；两端固定 μ=0.5；一端固定一端自由 μ=2.0。局部 y、z 两个方向可分别设置。</p>
    <div class="table-wrap"><table id="stabilityMemberTable" class="stability-table"><thead><tr><th>杆件</th><th>y 向端部约束</th><th>μy</th><th>z 向端部约束</th><th>μz</th><th>说明</th></tr></thead><tbody></tbody></table></div>
    <div class="actions"><button id="runStabilityCheck">计算构件稳定性</button></div>
    <p id="stabilityHint" class="help">有效长度系数是边界条件的工程近似。点击计算后，将先更新整体刚架结果，再按受压内力扫描各杆。</p>
    <div id="stabilitySummary"></div>`;
  anchor.insertAdjacentElement('beforebegin', panel);

  const supportOptions = [
    ['default', '使用默认值'], ['pinned', '两端铰支'], ['fixedPinned', '一端固定一端铰支'],
    ['fixed', '两端固定'], ['cantilever', '一端固定一端自由'], ['custom', '自定义'],
  ];
  const supportMu = {pinned: 1.0, fixedPinned: 0.7, fixed: 0.5, cantilever: 2.0};
  let memberSettings = {};
  let latest = null;
  const number = selector => Number(document.querySelector(selector).value);
  const defaultMu = axis => number(axis === 'y' ? '#stabilityDefaultMuY' : '#stabilityDefaultMuZ');
  const validMu = value => Number.isFinite(value) && value > 0;
  const text = value => Number.isFinite(value) ? value.toFixed(2) : '—';
  const options = (selected, axis) => supportOptions.map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${value === 'default' ? `${label} μ${axis}=${defaultMu(axis).toFixed(2)}` : label}</option>`).join('');
  const stateFor = element => memberSettings[element] || {typeY: 'default', typeZ: 'default', muY: defaultMu('y'), muZ: defaultMu('z')};
  const configuredMu = (state, axis) => {
    const type = axis === 'y' ? state.typeY : state.typeZ;
    const stored = axis === 'y' ? state.muY : state.muZ;
    return type === 'default' ? defaultMu(axis) : type === 'custom' ? Number(stored) : supportMu[type];
  };
  const renderRows = () => {
    const rows = (data.elements || []).map(element => Number(element.id));
    const body = document.querySelector('#stabilityMemberTable tbody');
    memberSettings = Object.fromEntries(rows.map(id => [id, stateFor(id)]));
    body.innerHTML = rows.map(id => {
      const state = stateFor(id), muY = configuredMu(state, 'y'), muZ = configuredMu(state, 'z');
      return `<tr data-element="${id}"><td>E${id}</td><td><select data-axis="y">${options(state.typeY, 'y')}</select></td><td><input data-mu="y" type="number" min="0.01" step="0.01" value="${muY}" ${state.typeY === 'custom' ? '' : 'disabled'}></td><td><select data-axis="z">${options(state.typeZ, 'z')}</select></td><td><input data-mu="z" type="number" min="0.01" step="0.01" value="${muZ}" ${state.typeZ === 'custom' ? '' : 'disabled'}></td><td class="help">y、z 主轴分别校核</td></tr>`;
    }).join('');
    body.querySelectorAll('select[data-axis]').forEach(select => select.onchange = () => {
      const row = select.closest('tr'), id = Number(row.dataset.element), axis = select.dataset.axis, state = stateFor(id);
      if (axis === 'y') state.typeY = select.value; else state.typeZ = select.value;
      if (select.value !== 'custom' && select.value !== 'default') {
        if (axis === 'y') state.muY = supportMu[select.value]; else state.muZ = supportMu[select.value];
      }
      memberSettings[id] = state; renderRows();
    });
    body.querySelectorAll('input[data-mu]').forEach(input => input.onchange = () => {
      const row = input.closest('tr'), id = Number(row.dataset.element), axis = input.dataset.mu, state = stateFor(id);
      if (axis === 'y') state.muY = Number(input.value); else state.muZ = Number(input.value);
      memberSettings[id] = state;
    });
  };
  window.frameCAERefreshStability = renderRows;
  const settings = () => {
    const defaultY = defaultMu('y'), defaultZ = defaultMu('z');
    if (!validMu(defaultY) || !validMu(defaultZ)) throw Error('默认有效长度系数 μy、μz 必须是正数。');
    const members = (data.elements || []).map(item => {
      const id = Number(item.id), state = stateFor(id), muY = configuredMu(state, 'y'), muZ = configuredMu(state, 'z');
      if (!validMu(muY) || !validMu(muZ)) throw Error(`E${id} 的有效长度系数必须是正数。`);
      return {element: id, muY, muZ};
    });
    return {defaultMuY: defaultY, defaultMuZ: defaultZ, members};
  };
  const status = message => { document.querySelector('#status').textContent = message; };
  const error = message => { const box = document.querySelector('#error'); box.textContent = message; box.style.display = 'block'; };
  const grade = utilization => utilization <= .8 ? ['稳定储备充足', 'stability-good'] : utilization <= 1 ? ['接近临界', 'stability-warn'] : ['不满足稳定要求', 'stability-fail'];
  const force = value => `${(value / 1e3).toFixed(2)} kN`;
  const renderChart = entries => {
    const width = 760, height = 240, left = 48, right = 18, top = 25, bottom = 42;
    const max = entries.reduce((m,item) => Math.max(m,item.utilization * 1.15),1.2);
    const chartHeight = height - top - bottom, chartWidth = width - left - right;
    const y = value => top + chartHeight * (1 - Math.min(value, max) / max);
    const bars = entries.map((item, index) => {
      const slot = chartWidth / entries.length, barWidth = Math.max(10, slot - 12), x = left + index * slot + (slot - barWidth) / 2, barY = y(item.utilization);
      const color = item.utilization > 1 ? '#dc4d61' : item.utilization > .8 ? '#e6a039' : '#37958c';
      return `<g><title>E${item.element}: η=${item.utilization.toFixed(3)}，N=${force(item.axialForce)}，Pcr=${force(item.pcr)}</title><rect x="${x}" y="${barY}" width="${barWidth}" height="${top + chartHeight - barY}" rx="3" fill="${color}"/><text x="${x + barWidth / 2}" y="${height - 18}" text-anchor="middle" font-size="11" fill="#40516a">E${item.element}</text></g>`;
    }).join('');
    return `<div style="border:1px solid #d7e1ef;border-radius:9px;padding:10px;background:#fbfdff"><strong>受压杆稳定利用率排序</strong><span class="help">　虚线：η=0.80；红线：η=1.00。悬停柱体可查看数值。</span><svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block;margin-top:6px"><line x1="${left}" y1="${top}" x2="${left}" y2="${top + chartHeight}" stroke="#9aa9bc"/><line x1="${left}" y1="${top + chartHeight}" x2="${width - right}" y2="${top + chartHeight}" stroke="#9aa9bc"/><line x1="${left}" y1="${y(.8)}" x2="${width - right}" y2="${y(.8)}" stroke="#d8891e" stroke-dasharray="5 4"/><text x="${left + 4}" y="${y(.8) - 4}" font-size="11" fill="#a85d00">η=0.80</text><line x1="${left}" y1="${y(1)}" x2="${width - right}" y2="${y(1)}" stroke="#cf3e4a" stroke-dasharray="5 4"/><text x="${left + 4}" y="${y(1) - 4}" font-size="11" fill="#b42330">η=1.00</text><text x="4" y="${top + 8}" font-size="11" fill="#40516a">利用率 η</text>${bars}</svg></div>`;
  };
  const renderResults = answer => {
    const compressed = answer.members.filter(item => item.status === 'compression').sort((a, b) => b.utilization - a.utilization);
    const rows = (document.querySelector('#stabilityShowTension').checked ? answer.members : compressed).map(item => {
      if (item.status !== 'compression') return `<tr><td>E${item.element}</td><td colspan="9" class="help">受拉或零轴力：不需压杆稳定校核。</td></tr>`;
      const [label, css] = grade(item.utilization);
      return `<tr><td>E${item.element}</td><td>${force(item.axialForce)}</td><td>${item.muY.toFixed(2)} / ${item.muZ.toFixed(2)}</td><td>${text(item.slendernessY)} / ${text(item.slendernessZ)}</td><td>${force(item.pcrY)}</td><td>${force(item.pcrZ)}</td><td>局部 ${item.governingAxis}</td><td>${force(item.pcr)}</td><td>${(item.utilization * 100).toFixed(1)}%</td><td class="stability-status ${css}">${label}</td></tr>`;
    }).join('');
    const critical = answer.critical;
    if (!critical) {
      document.querySelector('#stabilitySummary').innerHTML = `<div class="stability-card"><b>结论</b><strong class="stability-good">当前荷载下没有受压杆</strong><p class="help">所有杆件均为受拉或零轴力，因此不需要 Euler 压杆稳定校核。</p></div>`;
      return;
    }
    const [label, css] = grade(critical.utilization);
    document.querySelector('#stabilitySummary').innerHTML = `<div class="stability-cards"><div class="stability-card"><b>最大稳定利用率 ηmax</b><strong class="${css}">${critical.utilization.toFixed(3)}</strong></div><div class="stability-card"><b>最危险受压杆</b><strong>E${critical.element}</strong></div><div class="stability-card"><b>最大压力 NEd</b><strong>${force(critical.axialForce)}</strong></div><div class="stability-card"><b>控制临界力 Pcr（局部 ${critical.governingAxis}）</b><strong>${force(critical.pcr)}</strong></div></div><p class="stability-status ${css}">结论：${label}。受压杆 ${answer.summary.compressionMemberCount} 根；储备充足 ${answer.summary.passCount} 根，接近临界 ${answer.summary.warningCount} 根，不满足 ${answer.summary.failCount} 根。</p>${renderChart(compressed)}<div class="table-wrap"><table class="stability-table"><thead><tr><th>杆件</th><th>最大压力 NEd</th><th>μy / μz</th><th>λy / λz</th><th>Pcr,y</th><th>Pcr,z</th><th>控制轴</th><th>Pcr</th><th>利用率</th><th>结论</th></tr></thead><tbody>${rows}</tbody></table></div><p class="help">${answer.assumptions.join(' ')}</p>`;
  };
  document.querySelector('#stabilityDefaultMuY').onchange = renderRows;
  document.querySelector('#stabilityDefaultMuZ').onchange = renderRows;
  document.querySelector('#stabilityShowTension').onchange = () => { if (latest) renderResults(latest); };
  document.querySelector('#runStabilityCheck').onclick = async () => {
    const action=document.querySelector('#runStabilityCheck');if(action.disabled)return;action.disabled=true;
    document.querySelector('#error').style.display = 'none';
    try {
      const configured = settings();
      status('正在更新整体刚架并扫描受压杆件…');
      const pending=JSON.stringify([payload(),settings()]);
      await solve();
      if (document.querySelector('#error').style.display !== 'none') throw Error(document.querySelector('#error').textContent);
      if (pending!==JSON.stringify([payload(),settings()])) throw Error('计算期间参数已修改，请重新计算。');
      if (!result) throw Error('整体刚架未能完成求解。');
      const response = await fetch('/api/stability-check', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({model: payload(), settings: configured})});
      const answer = await response.json();
      if (!response.ok) throw Error(answer.error || '稳定校核失败。');
      if (pending!==JSON.stringify([payload(),settings()])) throw Error('计算期间参数已修改，本次结果未应用，请重新计算。');
      latest = answer; renderResults(answer);
      window.dispatchEvent(new CustomEvent('framecae:check-result', {detail:{kind:'stability',answer}}));
      const critical = answer.critical;
      document.querySelector('#results').textContent += critical ? `\n\nEuler 稳定校核完成：最危险受压杆 E${critical.element}，利用率 η=${critical.utilization.toFixed(3)}，控制轴为局部 ${critical.governingAxis}。` : '\n\nEuler 稳定校核完成：当前工况没有受压杆。';
      status('Euler 构件稳定校核完成。');
    } catch (caught) { error(caught.message); status('稳定校核参数需要修正。'); } finally { action.disabled=false; }
  };
  renderRows();
})();
