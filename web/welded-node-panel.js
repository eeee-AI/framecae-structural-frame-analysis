(() => {
  const generic = document.querySelector('#genericLocalSettings');
  if (!generic || document.querySelector('#weldedConnectionSettings')) return;
  const style = document.createElement('style');
  style.textContent = `#weldedConnectionSettings{margin-top:9px;padding:9px;border:1px solid #d9e4ef;border-radius:8px;background:#f9fcff}#weldedConnectionSettings h4{margin:0 0 7px;color:#244d7b;font-size:14px}.weld-check{display:flex;align-items:center;gap:6px;margin-top:7px;font-size:12px;color:#486078}.weld-badge{display:inline-block;padding:2px 6px;border-radius:99px;background:#e7f3ea;color:#217647;font-size:12px}`;
  document.head.append(style);
  const box = document.createElement('section');
  box.id = 'weldedConnectionSettings';
  box.innerHTML = `
    <h4>连接构造：<span class="weld-badge">直接焊接圆管节点</span></h4>
    <div class="local-grid">
      <label>连接类型 <select id="genericConnectionType"><option value="directWeldedCHS">自动：马鞍口／斜切闭合</option></select></label>
      <label>焊脚尺寸 z (m) <input id="genericWeldLeg" type="number" min="0" step="0.001" placeholder="留空：按壁厚自动建议"></label>
      <label>焊趾圆角 r (m) <input id="genericToeRadius" type="number" min="0" step="0.001" placeholder="留空：按焊脚自动建议"></label>
      <label><input id="genericShowWeld" type="checkbox" checked> 标出实际焊缝网格</label>
    </div>
    <p id="genericWeldHint" class="help">有共线主管时采用马鞍口；无共线主管的等截面转角节点采用斜切闭合拼接，保留内部管腔。留空时焊脚取最小壁厚的 0.70 倍，圆角取焊脚的 0.25 倍，并用于本次诊断计算；评价实际焊缝请填写设计或测量尺寸。</p>
    <p class="help">03 已同步 01 的截断面位移和转角，并传递实体自重。局部区域内直接受力尚需实际施力表面；不支持的加载会在计算前提示。远端受力与连接处直接受力是不同工况，不能随意替换。</p>`;
  generic.append(box);

  const baseSettings = genericLocalSettings;
  genericLocalSettings = () => ({
    ...baseSettings(),
    connectionType: document.querySelector('#genericConnectionType').value,
    weldLeg: document.querySelector('#genericWeldLeg').value,
    toeRadius: document.querySelector('#genericToeRadius').value,
  });
  const baseSetSettings = setGenericLocalSettings;
  setGenericLocalSettings = settings => {
    baseSetSettings(settings);
    if (settings.connectionType) document.querySelector('#genericConnectionType').value = settings.connectionType;
    if (settings.weldLeg !== undefined && settings.weldLeg !== null) document.querySelector('#genericWeldLeg').value = settings.weldLeg;
    if (settings.toeRadius !== undefined && settings.toeRadius !== null) document.querySelector('#genericToeRadius').value = settings.toeRadius;
  };

  const previousWriteGeneric = writeGenericResults;
  writeGenericResults = function () {
    previousWriteGeneric();
    const connection = localResult?.connection;
    if (!connection) return;
    const check = connection.geometryChecks || {};
    const weld = `连接构造：直接焊接圆管节点（${check.miterCutApplied ? '等截面斜切闭合 + ' : '主管马鞍口 + '}${connection.continuousAllAround ? '连续环焊缝' : '非连续焊缝'}）\n焊脚 z=${Number(connection.weldLeg).toExponential(4)} m，焊趾圆角 r=${Number(connection.toeRadius).toExponential(4)} m，来源：${connection.weldGeometrySource}\n几何检查：${check.allHex8 ? '全 Hex8' : '非 Hex8'}；${check.singleSolidComponent ? '实体单连通' : '发现多连通实体'}；${check.junctionClosed ? '管腔保留，实际网格封截口后无泄漏' : '接头闭合检查未通过'}。`;
    document.querySelector('#results').textContent += `\n${weld}`;
  };

  document.querySelector('#genericShowWeld').onchange = () => draw();
  const previousConvergenceResults = writeConvergenceResults;
  writeConvergenceResults = function () {
    previousConvergenceResults();
    if (convergenceResult?.convergenceScope !== 'fixedSurfaceHotspotOnly') return;
    const results = document.querySelector('#results');
    results.textContent = results.textContent.replace('本节点局部应力集中结果通过收敛检验', '固定热点恢复应力通过数值收敛检验');
    results.textContent += `\n${convergenceResult.notice}\n停止原因：${convergenceResult.stoppedReason}`;
  };
})();
