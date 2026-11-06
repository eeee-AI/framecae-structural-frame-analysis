(() => {
  const editor = document.querySelector('#editor');
  const anchor = document.querySelector('#genericLocalSettings') || document.querySelector('#localSettings');
  if (!editor || document.querySelector('#strengthCheckSettings')) return;

  const style = document.createElement('style');
  style.textContent = `
    #strengthCheckSettings{border:0;padding:0}#strengthCheckSettings summary{font-size:19px;padding:3px 0 10px;border-bottom:1px solid #d9e4ef}#strengthCheckSettings>p.help:first-of-type{margin:9px 0}.strength-control-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-items:center}.strength-control-grid label{display:flex;align-items:center;gap:5px;font-size:12px}.strength-control-grid input{min-width:0;width:100%;border:1px solid #d7e1ee;background:#fff;padding:5px}.strength-actions{display:flex;align-items:center;gap:10px;margin:9px 0;flex-wrap:wrap}.strength-result-layout{display:grid;grid-template-columns:1fr;gap:10px;align-items:start;margin-top:10px}.strength-result-card{border:1px solid #d7e2ef;border-radius:9px;padding:10px;background:#fbfdff}.strength-result-card table{font-size:12px}.strength-result-card th,.strength-result-card td{padding:5px}.strength-analysis-card{min-width:0}@media(max-width:650px){.strength-control-grid{grid-template-columns:1fr}}
  `;
  document.head.append(style);

  const panel = document.createElement('details');
  panel.id = 'strengthCheckSettings';
  panel.open = true;
  panel.innerHTML = `
    <summary>整体危险截面：四大强度理论校核</summary>
    <p class="help">基于整体梁的 N、V、T、M 连续求解危险位置；这是名义截面强度校核，不替代焊缝、孔洞与相贯节点的局部应力集中分析。正式圆管设计应使用彼此一致的 A、Iy、Iz、J、D。</p>
    <div class="strength-control-grid">
      <label>屈服强度 fy (MPa) <input id="strengthFy" value="355"></label>
      <label>抗拉强度 ft (MPa) <input id="strengthFt" value="355"></label>
      <label>抗压强度 fc (MPa) <input id="strengthFc" value="355"></label>
      <label>极值相对容差 <input id="strengthTolerance" type="number" min="0.0000000001" max="0.01" value="0.000001"></label>
      <label><input id="strengthShear" type="checkbox" checked> 计入平均横向剪应力</label>
    </div>
    <div class="strength-actions"><button id="runStrengthCheck">计算四大理论危险截面</button><span id="strengthHint" class="help">校核使用第一模块已确认结构的材料、截面、边界条件及荷载。</span></div>
    <div id="strengthSummary" class="help"></div>`;
  anchor.insertAdjacentElement('beforebegin', panel);

  const status = text => { document.querySelector('#status').textContent = text; };
  const error = text => { const box = document.querySelector('#error'); box.textContent = text; box.style.display = 'block'; };
  const settings = () => ({
    yieldStrength: Number(document.querySelector('#strengthFy').value) * 1e6,
    tensileStrength: Number(document.querySelector('#strengthFt').value) * 1e6,
    compressiveStrength: Number(document.querySelector('#strengthFc').value) * 1e6,
    extremumTolerance: Number(document.querySelector('#strengthTolerance').value),
    includeAverageTransverseShear: document.querySelector('#strengthShear').checked,
  });
  const setCase = async (loads, title) => {
    data.loads = loads;
    localResult = null; convergenceResult = null; displayMode = 'global';
    renderTables();
    document.querySelector('#results').textContent = `已载入${title}，正在自动更新整体三维结果。`;
    document.querySelector('#strengthHint').textContent = `${title}已写入可编辑的节点荷载表。`;
    status(`${title}已载入，正在求解整体刚架…`);
    await solve();
    if (result) {
      document.querySelector('#strengthHint').textContent = `${title}已求解。可直接查看三维结果，或继续点击“四大理论危险截面”执行材料校核。`;
      status(`${title}整体三维结果已更新。`);
    }
  };
  const gravityCaseButton = document.querySelector('#strengthGravity'); if (gravityCaseButton) gravityCaseButton.onclick = () => setCase(
    [5, 6, 7, 8].map(node => ({node, fx: 0, fy: 0, fz: -35000, mx: 0, my: 0, mz: 0})),
    '竖向荷载工况',
  );
  const windCaseButton = document.querySelector('#strengthWind'); if (windCaseButton) windCaseButton.onclick = () => setCase(
    [5, 6, 7, 8].map(node => ({node, fx: 60000, fy: 0, fz: -20000, mx: 0, my: 0, mz: 0})),
    '侧向风荷载工况',
  );
  const eccentricCaseButton = document.querySelector('#strengthEccentric'); if (eccentricCaseButton) eccentricCaseButton.onclick = () => setCase([
    {node: 5, fx: 45000, fy: 0, fz: -18000, mx: 0, my: 0, mz: 0},
    {node: 6, fx: 70000, fy: 0, fz: -18000, mx: 0, my: 0, mz: 10000},
    {node: 7, fx: 90000, fy: -25000, fz: -18000, mx: 0, my: 0, mz: 15000},
    {node: 8, fx: 50000, fy: -25000, fz: -18000, mx: 0, my: 0, mz: 5000},
  ], '偏心风＋扭矩工况');

  const labels = {rankine: 'Rankine 最大主应力', strain: 'Saint-Venant 最大主应变', tresca: 'Tresca 最大切应力', mises: 'von Mises 畸变能'};
  let latestStrength = null;
  const riskColor = value => value > 1 ? '#dc4d61' : value > .8 ? '#e6a039' : '#37958c';
  const renderStrengthVisual = theory => {
    if (!latestStrength) return;
    const critical = latestStrength.theories[theory].critical;
    const members = [...latestStrength.memberUtilizations].sort((a, b) => a.element - b.element);
    const maxValue = members.reduce((m,member) => Math.max(m, member[theory] * 1.1), 1.2);
    const width = 760, height = 230, left = 44, right = 14, top = 28, bottom = 42;
    const chartWidth = width - left - right, chartHeight = height - top - bottom;
    const barWidth = Math.max(12, chartWidth / members.length - 14);
    const x = index => left + index * chartWidth / members.length + (chartWidth / members.length - barWidth) / 2;
    const y = value => top + chartHeight * (1 - Math.min(value, maxValue) / maxValue);
    const threshold = y(1);
    const bars = members.map((member, index) => {
      const value = member[theory], barY = y(value), selected = member.element === critical.element;
      return `<g><rect x="${x(index)}" y="${barY}" width="${barWidth}" height="${top + chartHeight - barY}" rx="3" fill="${riskColor(value)}" opacity="${selected ? 1 : .78}"/>${selected ? `<rect x="${x(index) - 2}" y="${barY - 2}" width="${barWidth + 4}" height="${top + chartHeight - barY + 4}" rx="4" fill="none" stroke="#101828" stroke-width="2"/>` : ''}<text x="${x(index) + barWidth / 2}" y="${height - 19}" text-anchor="middle" font-size="11" fill="#40516a">E${member.element}</text></g>`;
    }).join('');
    const ratio = Math.max(0, Math.min(1, critical.position / Math.max(critical.elementLength, 1e-12)));
    const safe = critical.utilizations[theory] > 1e-12 ? 1 / critical.utilizations[theory] : Infinity;
    document.querySelector('#strengthVisual').innerHTML = `
      <div style="display:flex;gap:7px;flex-wrap:wrap;margin:10px 0">${Object.keys(labels).map(key => `<button class="secondary strength-theory" data-theory="${key}">${labels[key]}</button>`).join('')}</div>
      <div style="border:1px solid #d7e1ef;border-radius:8px;padding:10px;background:#fbfdff">
        <strong>${labels[theory]}：危险截面 E${critical.element}，x = ${critical.position.toFixed(3)} / ${critical.elementLength.toFixed(3)} m</strong><br>
        <span class="help">等效应力 ${(critical.equivalentStresses[theory] / 1e6).toFixed(2)} MPa；利用率 ${(critical.utilizations[theory] * 100).toFixed(1)}%；安全系数 ${Number.isFinite(safe) ? safe.toFixed(2) : '∞'}。柱状图显示每根杆的最大利用率，黑框为危险杆件。</span>
        <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;display:block;margin-top:6px" aria-label="杆件利用率图">
          <line x1="${left}" y1="${top}" x2="${left}" y2="${top + chartHeight}" stroke="#9aa9bc"/><line x1="${left}" y1="${top + chartHeight}" x2="${width - right}" y2="${top + chartHeight}" stroke="#9aa9bc"/>
          <line x1="${left}" y1="${threshold}" x2="${width - right}" y2="${threshold}" stroke="#d83a46" stroke-dasharray="5 4"/><text x="${left + 3}" y="${threshold - 4}" font-size="11" fill="#b42330">100% 允许值</text><text x="4" y="${top + 8}" font-size="11" fill="#40516a">利用率</text>${bars}
        </svg>
        <div style="margin:2px 10px 3px 10px"><span class="help">危险截面在 E${critical.element} 上的位置</span><div style="height:15px;background:#dce6f2;border-radius:8px;position:relative"><span style="position:absolute;left:${(ratio * 100).toFixed(2)}%;top:-4px;width:4px;height:23px;background:#d83a46;border-radius:2px" title="x/L=${ratio.toFixed(3)}"></span></div><div style="display:flex;justify-content:space-between" class="help"><span>起点 x=0</span><span>红线：x/L=${ratio.toFixed(3)}</span><span>终点 x=L</span></div></div>
      </div>`;
    document.querySelectorAll('.strength-theory').forEach(button => {
      button.onclick = () => { renderStrengthVisual(button.dataset.theory); window.dispatchEvent(new CustomEvent('framecae:strength-theory', {detail:{theory:button.dataset.theory}})); };
      if (button.dataset.theory === theory) button.style.background = '#1671c9', button.style.color = '#fff';
    });
  };
  document.querySelector('#runStrengthCheck').onclick = async () => {
    const action=document.querySelector('#runStrengthCheck');if(action.disabled)return;action.disabled=true;
    document.querySelector('#error').style.display = 'none';
    status('正在求解整体刚架并计算危险截面…');
    try {
      const pending=JSON.stringify([payload(),settings()]);
      await solve();
      if (document.querySelector('#error').style.display !== 'none') throw Error(document.querySelector('#error').textContent);
      if (pending!==JSON.stringify([payload(),settings()])) throw Error('计算期间参数已修改，请重新计算。');
      if (!result) throw Error('整体刚架未能完成求解。');
      const response = await fetch('/api/strength-check', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model: payload(), settings: settings()}),
      });
      const answer = await response.json();
      if (!response.ok) throw Error(answer.error || '强度校核失败。');
      if (pending!==JSON.stringify([payload(),settings()])) throw Error('计算期间参数已修改，本次结果未应用，请重新计算。');
      latestStrength = answer;
      const rows = Object.entries(answer.theories).map(([key, item]) => {
        const point = item.critical, utilization = point.utilizations[key];
        const equivalent = point.equivalentStresses[key] / 1e6;
        const safety = utilization > 1e-15 ? 1 / utilization : Infinity;
        return `<tr><td>${labels[key]}</td><td>E${point.element}</td><td>${point.position.toFixed(3)}</td><td>${point.angleDegrees.toFixed(1)}°</td><td>${equivalent.toFixed(2)}</td><td>${(utilization * 100).toFixed(1)}%</td><td>${Number.isFinite(safety) ? safety.toFixed(2) : '∞'}</td></tr>`;
      }).join('');
      document.querySelector('#strengthSummary').innerHTML = `<div class="strength-result-layout"><section class="strength-result-card"><table><thead><tr><th>理论</th><th>危险杆件</th><th>x (m)</th><th>周向角</th><th>等效应力 (MPa)</th><th>利用率</th><th>安全系数</th></tr></thead><tbody>${rows}</tbody></table><p class="help">连续极值求解，共核验 ${answer.pointCount} 个实际位置候选点；相对容差 ${answer.extremumTolerance}。${answer.assumptions[0]}</p></section><section class="strength-result-card strength-analysis-card"><div id="strengthVisual"></div></section></div>`;
      renderStrengthVisual('mises');
      window.dispatchEvent(new CustomEvent('framecae:check-result', {detail:{kind:'strength',answer,theory:'mises'}}));
      const mises = answer.theories.mises.critical;
      document.querySelector('#results').textContent += `\n\n四大强度理论校核完成：von Mises 危险截面为 E${mises.element}，x=${mises.position.toFixed(3)} m，利用率 ${(mises.utilizations.mises * 100).toFixed(1)}%。`;
      status('四大强度理论危险截面校核完成。');
    } catch (caught) { error(caught.message); status('强度校核参数需要修正。'); } finally { action.disabled=false; }
  };
})();
