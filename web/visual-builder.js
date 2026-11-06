(() => {
  const editor = document.querySelector('#editor');
  const tables = document.querySelector('#tables');
  if (!editor || !tables || document.querySelector('#visualBuilderSettings')) return;

  const style = document.createElement('style');
  style.textContent = `
    #visualBuilderSettings .builder-layout{display:grid;grid-template-columns:minmax(190px,250px) minmax(0,1fr);gap:12px;align-items:stretch}.builder-tools{padding:12px;border:1px solid #d8e3ef;border-radius:9px;background:#fbfdff}.builder-tools .actions{display:grid;grid-template-columns:1fr;gap:7px}.builder-tools label{display:flex;align-items:center;gap:7px;margin:9px 0;font-size:13px;color:#40516a}.builder-tools input[type=number]{width:82px}.builder-canvas-wrap{min-height:420px;border:1px solid #c8d8e9;border-radius:9px;overflow:hidden;background:linear-gradient(135deg,#fbfdff,#eff5fc)}#builderCanvas{width:100%;height:420px;display:block;touch-action:none;cursor:grab}.builder-canvas-wrap.drag-node #builderCanvas{cursor:grabbing}.builder-selection{margin:10px 0 0;padding:8px 10px;border-left:3px solid #2b78c5;background:#f4f8fd;color:#40516a;font-size:13px;line-height:1.55}.builder-key{font-size:12px;color:#61748c;margin-top:8px}.builder-status{min-height:20px;margin:8px 0 0;color:#1b5e9e;font-size:13px}@media(max-width:850px){#visualBuilderSettings .builder-layout{grid-template-columns:1fr}.builder-canvas-wrap,#builderCanvas{min-height:340px;height:340px}}
  `;
  document.head.append(style);

  const panel = document.createElement('details');
  panel.id = 'visualBuilderSettings';
  panel.open = true;
  panel.innerHTML = `
    <summary>可视化三维建模</summary>
    <p class="help">在三维点阵中创建杆件；拖动节点后，端点会在松开鼠标时吸附到最近网格点。相同网格点的节点会自动合并，杆件、节点号及起终点关系会同步到下方表格。</p>
    <div class="builder-layout">
      <div class="builder-tools">
        <div class="actions">
          <button id="builderNewBeam">新建杆件</button>
          <button id="builderConfirmModel">确认并计算</button>
          <button id="builderUndo" class="secondary" disabled>撤回上一步</button>
          <button id="builderDeleteBeam" class="secondary">删除选中杆件</button>
          <button id="builderDeleteNode" class="secondary">删除选中节点</button>
          <button id="builderClear" class="secondary">清空图形模型</button>
          <button id="builderResetView" class="secondary">重置观察视角</button>
        </div>
        <label>网格间距 <input id="builderGridStep" type="number" min="0.05" step="0.05" value="2.00"> m</label>
        <label><input id="builderGridVisible" type="checkbox" checked> 显示三维网格</label>
        <label><input id="builderNodeLabels" type="checkbox" checked> 显示节点号</label>
        <label><input id="builderElementLabels" type="checkbox" checked> 显示杆件号</label>
        <hr style="border:0;border-top:1px solid #d9e4ef;margin:12px 0">
        <strong style="font-size:14px;color:#244d7b">几何约束</strong>
        <label>基准杆 <select id="builderConstraintA"></select></label>
        <label>调整杆 <select id="builderConstraintB"></select></label>
        <div class="actions">
          <button id="builderParallel" class="secondary">两杆平行</button>
          <button id="builderPerpendicular" class="secondary">两杆垂直</button>
        </div>
        <label>基准端 <select id="builderCoincidentA"><option value="start">起点</option><option value="end">终点</option></select></label>
        <label>调整端 <select id="builderCoincidentB"><option value="start">起点</option><option value="end">终点</option></select></label>
        <button id="builderCoincident" class="secondary" style="width:100%">两杆端点重合（合并节点）</button>
        <hr style="border:0;border-top:1px solid #d9e4ef;margin:12px 0">
        <strong style="font-size:14px;color:#244d7b">边界条件：位移／转角约束</strong>
        <div id="builderBCNode" class="help" style="margin:7px 0">请先在画布中选中一个节点。</div>
        <label><input id="builderBCux" data-bc="ux" type="checkbox"> U1 / ux <input id="builderBCuxValue" data-bc-value="ux" type="number" step="any" value="0"></label>
        <label><input id="builderBCuy" data-bc="uy" type="checkbox"> U2 / uy <input id="builderBCuyValue" data-bc-value="uy" type="number" step="any" value="0"></label>
        <label><input id="builderBCuz" data-bc="uz" type="checkbox"> U3 / uz <input id="builderBCuzValue" data-bc-value="uz" type="number" step="any" value="0"></label>
        <label><input id="builderBCrx" data-bc="rx" type="checkbox"> UR1 / rx <input id="builderBCrxValue" data-bc-value="rx" type="number" step="any" value="0"></label>
        <label><input id="builderBCry" data-bc="ry" type="checkbox"> UR2 / ry <input id="builderBCryValue" data-bc-value="ry" type="number" step="any" value="0"></label>
        <label><input id="builderBCrz" data-bc="rz" type="checkbox"> UR3 / rz <input id="builderBCrzValue" data-bc-value="rz" type="number" step="any" value="0"></label>
        <div class="actions"><button id="builderApplyBC" class="secondary">创建／更新边界条件</button><button id="builderClearBC" class="secondary">清除该节点边界条件</button></div>
        <div class="builder-key">勾选表示指定该自由度；值为 0 即固定。U1–U3 是平动，UR1–UR3 是转角，逻辑与 Abaqus 的 Displacement/Rotation 边界条件一致。</div>
        <hr style="border:0;border-top:1px solid #d9e4ef;margin:12px 0">
        <strong style="font-size:14px;color:#244d7b">荷载：集中力／力矩</strong>
        <div id="builderLoadNode" class="help" style="margin:7px 0">请先在画布中选中一个节点。</div>
        <label>F1 / Fx (N) <input id="builderLoadFx" data-load="fx" type="number" step="any" value="0"></label>
        <label>F2 / Fy (N) <input id="builderLoadFy" data-load="fy" type="number" step="any" value="0"></label>
        <label>F3 / Fz (N) <input id="builderLoadFz" data-load="fz" type="number" step="any" value="0"></label>
        <label>M1 / Mx (N·m) <input id="builderLoadMx" data-load="mx" type="number" step="any" value="0"></label>
        <label>M2 / My (N·m) <input id="builderLoadMy" data-load="my" type="number" step="any" value="0"></label>
        <label>M3 / Mz (N·m) <input id="builderLoadMz" data-load="mz" type="number" step="any" value="0"></label>
        <div class="actions"><button id="builderApplyLoad" class="secondary">创建／更新节点荷载</button><button id="builderClearLoad" class="secondary">清除该节点荷载</button></div>
        <div class="builder-key">F1–F3 为全局 X、Y、Z 方向集中力；M1–M3 为绕全局 X、Y、Z 的节点力矩。红色箭头表示已定义的力方向。</div>
        <div class="builder-key">拖空白处：旋转视角<br>滚轮：缩放<br>拖节点：移动并磁吸<br>点击杆件或节点：选择</div>
        <div id="builderSelection" class="builder-selection">未选择节点或杆件。</div>
      </div>
      <div class="builder-canvas-wrap"><canvas id="builderCanvas" aria-label="空间杆系图形化建模画布"></canvas></div>
    </div>
    <p id="builderStatus" class="builder-status">新建杆件后，系统会自动编号并填入节点表、杆件表。</p>`;
  tables.insertAdjacentElement('beforebegin', panel);

  const canvas = document.querySelector('#builderCanvas');
  const context = canvas.getContext('2d');
  const wrap = canvas.closest('.builder-canvas-wrap');
  const state = {yaw: -0.72, pitch: 0.50, zoom: 1, selectedNode: null, selectedElement: null, draggingNode: null, preview: null, aiDraft: null, cameraDrag: null, moved: false, confirmed: false};
  window.frameCAESelectedElement = () => state.selectedElement;
  // Rotation belongs to the model, shared with 01/02/03/04/05. Zoom remains
  // independent because the editable frame and the local solid have different extents.
  for (const axis of ['yaw','pitch']) Object.defineProperty(state, axis, {
    get: () => view[axis], set: value => { view[axis] = value; }, enumerable: true,
  });
  window.frameCAEBuilderCamera = () => ({yaw: state.yaw, pitch: state.pitch});
  window.frameCAEUpdateSections = sections => {
    recordHistory();data.sections=JSON.parse(JSON.stringify(sections));
    markModelDirty();result=null;localResult=null;convergenceResult=null;displayMode='global';
    renderTables();setConfirmButton();
  };
  const history = [];
  // ``data`` 是仍可编辑的建模草稿；确认后，后续分析统一读取这份活动快照。
  const editablePayload = payload;
  let confirmedPayload = null;
  payload = () => confirmedPayload ? JSON.parse(JSON.stringify(confirmedPayload)) : editablePayload();
  window.frameCAEHasConfirmedModel = () => confirmedPayload !== null && state.confirmed && Boolean(result);
  const requireConfirmedModel = event => {
    if (window.frameCAEHasConfirmedModel()) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const box = document.querySelector('#error'); box.textContent = '请先在“01 整体空间刚架求解”中完成建模、边界条件和荷载设置，并点击“确认并计算”。'; box.style.display = 'block';
    document.querySelector('#status').textContent = '后续模块只能分析第一模块中已确认的结构。';
  };
  const finite = value => Number.isFinite(Number(value));
  const number = value => finite(value) ? Number(value) : 0;
  const gridStep = () => Math.max(0.05, number(document.querySelector('#builderGridStep').value) || 2.0);
  const status = message => { document.querySelector('#builderStatus').textContent = message; };
  const setConfirmButton = () => { const button = document.querySelector('#builderConfirmModel'); button.textContent = state.confirmed ? '重新计算' : '确认并计算'; window.dispatchEvent(new CustomEvent('framecae:model-state')); };
  const markModelDirty = () => {
    confirmedPayload=null;state.confirmed=false;
    result=null;localResult=null;convergenceResult=null;verificationResult=null;displayMode='global';
    window.FrameCAESolidView?.hide();setConfirmButton();
    status('结构、荷载或参数已修改；旧01、03结果已失效，请点击“确认并计算”。');
  };
  window.frameCAEInvalidateModel = markModelDirty;
  const updateUndoButton = () => { document.querySelector('#builderUndo').disabled = history.length === 0; };
  const recordHistory = () => { history.push(JSON.stringify(data)); if (history.length > 50) history.shift(); updateUndoButton(); };
  const nodes = () => (data.nodes || []).filter(node => finite(node.id)).map(node => ({id: Number(node.id), x: number(node.x), y: number(node.y), z: number(node.z)}));
  const elements = () => (data.elements || []).filter(element => finite(element.id) && finite(element.start) && finite(element.end)).map(element => ({...element, id: Number(element.id), start: Number(element.start), end: Number(element.end)}));
  const nodeMap = () => new Map(nodes().map(node => [node.id, node]));
  const nextId = rows => Math.max(0, ...rows.map(row => Number(row.id)).filter(Number.isFinite)) + 1;
  const samePoint = (a, b, tolerance = 1.0e-8) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) <= tolerance;
  const snap = point => { const step = gridStep(); return {x: Math.round(point.x / step) * step, y: Math.round(point.y / step) * step, z: Math.round(point.z / step) * step}; };
  const updateSelection = () => {
    const node = state.selectedNode === null ? null : nodeMap().get(state.selectedNode);
    const element = state.selectedElement === null ? null : elements().find(item => item.id === state.selectedElement);
    const selection = document.querySelector('#builderSelection');
    if (node) {
      const connected = elements().filter(item => item.start === node.id || item.end === node.id).map(item => `E${item.id}`).join('、') || '无';
      selection.textContent = `已选 N${node.id}：(${node.x.toFixed(3)}, ${node.y.toFixed(3)}, ${node.z.toFixed(3)}) m；相连杆件：${connected}。`;
    } else if (element) {
      const byId = nodeMap(), start = byId.get(element.start), end = byId.get(element.end);
      const length = start && end ? Math.hypot(end.x - start.x, end.y - start.y, end.z - start.z) : NaN;
      selection.textContent = `已选 E${element.id}：N${element.start} → N${element.end}，L=${Number.isFinite(length) ? length.toFixed(3) : '—'} m，材料 ${element.material}，截面 ${element.section}。`;
    } else selection.textContent = '未选择节点或杆件。';
    window.frameCAERefreshBoundaryControls?.(); window.frameCAERefreshLoadControls?.();
    window.dispatchEvent(new CustomEvent('framecae:selection'));
  };
  const boundaryFields = ['ux', 'uy', 'uz', 'rx', 'ry', 'rz'];
  const boundaryRow = nodeId => (data.constraints || []).find(row => Number(row.node) === Number(nodeId));
  const refreshBoundaryControls = () => {
    const nodeId = state.selectedNode, row = nodeId === null ? null : boundaryRow(nodeId), available = nodeId !== null;
    document.querySelector('#builderBCNode').textContent = available ? `当前区域：节点 N${nodeId}${row ? '（已有边界条件）' : '（尚未定义边界条件）'}` : '请先在画布中选中一个节点。';
    boundaryFields.forEach(field => {
      const enabled = available && row && row[field] !== undefined && row[field] !== null && row[field] !== '';
      const check = document.querySelector(`[data-bc="${field}"]`), input = document.querySelector(`[data-bc-value="${field}"]`);
      check.checked = Boolean(enabled); check.disabled = !available; input.value = enabled ? row[field] : 0; input.disabled = !available || !enabled;
    });
    document.querySelector('#builderApplyBC').disabled = !available; document.querySelector('#builderClearBC').disabled = !available || !row;
  };
  window.frameCAERefreshBoundaryControls = refreshBoundaryControls;
  const loadFields = ['fx', 'fy', 'fz', 'mx', 'my', 'mz'];
  const loadRow = nodeId => (data.loads || []).find(row => Number(row.node) === Number(nodeId));
  const refreshLoadControls = () => {
    const nodeId = state.selectedNode, row = nodeId === null ? null : loadRow(nodeId), available = nodeId !== null;
    document.querySelector('#builderLoadNode').textContent = available ? `当前区域：节点 N${nodeId}${row ? '（已有节点荷载）' : '（尚未定义节点荷载）'}` : '请先在画布中选中一个节点。';
    loadFields.forEach(field => { const input = document.querySelector(`[data-load="${field}"]`); input.value = row?.[field] ?? 0; input.disabled = !available; });
    document.querySelector('#builderApplyLoad').disabled = !available; document.querySelector('#builderClearLoad').disabled = !available || !row;
  };
  window.frameCAERefreshLoadControls = refreshLoadControls;
  const refreshConstraintOptions = () => {
    const entries = elements(), setOptions = id => {
      const select = document.querySelector(id); if (!select) return;
      const previous = select.value;
      select.innerHTML = entries.map(item => `<option value="${item.id}">E${item.id}（N${item.start} → N${item.end}）</option>`).join('');
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
      else if (state.selectedElement !== null && [...select.options].some(option => Number(option.value) === state.selectedElement)) select.value = String(state.selectedElement);
    };
    setOptions('#builderConstraintA'); setOptions('#builderConstraintB');
    const first = document.querySelector('#builderConstraintA'), second = document.querySelector('#builderConstraintB');
    if (entries.length > 1 && first && second && first.value === second.value) second.value = String(entries.find(item => item.id !== Number(first.value))?.id ?? first.value);
  };
  const centerAndScale = () => {
    // AI 草案仅在用户选择预览时加入视域计算；未确认前不写入 data。
    const draftNodes = state.aiDraft?.model?.nodes || [];
    const list = [...nodes(), ...draftNodes.filter(node => finite(node.id)).map(node => ({id: Number(node.id), x: number(node.x), y: number(node.y), z: number(node.z)}))];
    const step = gridStep();
    if (!list.length) return {center: {x: 0, y: 0, z: 0}, range: step * 6};
    const low = {x: Infinity, y: Infinity, z: Infinity}, high = {x: -Infinity, y: -Infinity, z: -Infinity};
    list.forEach(node => ['x', 'y', 'z'].forEach(axis => { low[axis] = Math.min(low[axis], node[axis]); high[axis] = Math.max(high[axis], node[axis]); }));
    const center = {x: (low.x + high.x) / 2, y: (low.y + high.y) / 2, z: (low.z + high.z) / 2};
    const span = Math.max(high.x - low.x, high.y - low.y, high.z - low.z, step * 5);
    return {center, range: Math.max(span * 1.25, step * 6)};
  };
  const projection = () => {
    const width = canvas.clientWidth, height = canvas.clientHeight, {center, range} = centerAndScale();
    const pixels = Math.min(width, height) * 0.40 / Math.max(range, 1.0e-9) * state.zoom;
    const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw), cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
    return {
      center, pixels,
      project(point) {
        const x = point.x - center.x, y = point.y - center.y, z = point.z - center.z;
        const p = window.FrameCAEModelView.projectOffset([x,y,z],state);
        return {x: width / 2 + p.x * pixels, y: height / 2 + p.y * pixels, depth: p.depth};
      },
      horizontal: {x: cy, y: -sy, z: 0}, vertical: {x: -sy * sp, y: -cy * sp, z: cp}, range,
    };
  };
  const setup = () => { const ratio = devicePixelRatio || 1, box = canvas.getBoundingClientRect(); canvas.width = Math.floor(box.width * ratio); canvas.height = Math.floor(box.height * ratio); context.setTransform(ratio, 0, 0, ratio, 0, 0); };
  const distanceToSegment = (point, first, second) => {
    const dx = second.x - first.x, dy = second.y - first.y, length2 = dx * dx + dy * dy;
    const ratio = length2 ? Math.max(0, Math.min(1, ((point.x - first.x) * dx + (point.y - first.y) * dy) / length2)) : 0;
    return Math.hypot(point.x - (first.x + ratio * dx), point.y - (first.y + ratio * dy));
  };
  const draw = () => {
    setup(); const width = canvas.clientWidth, height = canvas.clientHeight, view = projection(), byId = nodeMap();
    context.clearRect(0, 0, width, height); context.fillStyle = '#f8fbff'; context.fillRect(0, 0, width, height);
    const step = gridStep(), showGrid = document.querySelector('#builderGridVisible').checked;
    if (showGrid) {
      // 完整的三维立方体线框阵列：每一条 x、y、z 方向边都绘出，
      // 因而任意相邻八个格点围成一个真实可见的立方体网格单元。
      const count = Math.max(3, Math.min(7, Math.ceil(view.range / step)));
      const low = -count * step, high = count * step;
      const world = (x, y, z) => ({x: view.center.x + x, y: view.center.y + y, z: view.center.z + z});
      const line = (first, second) => {
        const a = view.project(first), b = view.project(second);
        context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
      };
      context.lineWidth = .72; context.strokeStyle = '#b4c9df'; context.globalAlpha = .46;
      // x 方向立方体边
      for (let iy = -count; iy <= count; iy++) for (let iz = -count; iz <= count; iz++) line(world(low, iy * step, iz * step), world(high, iy * step, iz * step));
      // y 方向立方体边
      for (let ix = -count; ix <= count; ix++) for (let iz = -count; iz <= count; iz++) line(world(ix * step, low, iz * step), world(ix * step, high, iz * step));
      // z 方向立方体边
      for (let ix = -count; ix <= count; ix++) for (let iy = -count; iy <= count; iy++) line(world(ix * step, iy * step, low), world(ix * step, iy * step, high));
      context.globalAlpha = 1;
    }
    const axisOrigin = view.project({x: 0, y: 0, z: 0}), axisLength = Math.max(step * 3, view.range * .45);
    [['x', '#d33c4a'], ['y', '#1b9b61'], ['z', '#2871cf']].forEach(([axis, color]) => {
      const vector = {x: axis === 'x' ? axisLength : 0, y: axis === 'y' ? axisLength : 0, z: axis === 'z' ? axisLength : 0}; const end = view.project(vector);
      context.strokeStyle = color; context.lineWidth = 1.5; context.beginPath(); context.moveTo(axisOrigin.x, axisOrigin.y); context.lineTo(end.x, end.y); context.stroke(); context.fillStyle = color; context.font = '12px sans-serif'; context.fillText(axis.toUpperCase(), end.x + 4, end.y - 3);
    });
    const drawElements = elements().map(element => ({element, first: byId.get(element.start), second: byId.get(element.end)})).filter(item => item.first && item.second).sort((a, b) => (view.project(a.first).depth + view.project(a.second).depth) - (view.project(b.first).depth + view.project(b.second).depth));
    drawElements.forEach(({element, first, second}) => {
      const a = view.project(first), b = view.project(second), selected = element.id === state.selectedElement;
      context.strokeStyle = selected ? '#e88a16' : '#246fb7'; context.lineWidth = selected ? 7 : 5; context.lineCap = 'round'; context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
      context.strokeStyle = selected ? '#fff5dc' : '#b8d2ea'; context.lineWidth = selected ? 2 : 1; context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
      if (document.querySelector('#builderElementLabels').checked) { context.fillStyle = selected ? '#9a4f00' : '#184d82'; context.font = 'bold 12px sans-serif'; context.fillText(`E${element.id}`, (a.x + b.x) / 2 + 5, (a.y + b.y) / 2 - 5); }
    });
    // AI 草案是独立紫色虚线层。它只借用画布投影，不修改当前节点、杆件或表格。
    if (state.aiDraft?.model?.nodes?.length && state.aiDraft?.model?.elements?.length) {
      const draftNodes = new Map(state.aiDraft.model.nodes.map(node => [Number(node.id), {x: number(node.x), y: number(node.y), z: number(node.z)}]));
      context.save(); context.setLineDash([7, 5]); context.strokeStyle = '#7b4fc8'; context.lineWidth = 3; context.globalAlpha = .9;
      state.aiDraft.model.elements.forEach(element => {
        const first = draftNodes.get(Number(element.start)), second = draftNodes.get(Number(element.end)); if (!first || !second) return;
        const a = view.project(first), b = view.project(second); context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
      });
      context.setLineDash([]); context.fillStyle = '#7142b6';
      draftNodes.forEach((node, id) => { const point = view.project(node); context.beginPath(); context.arc(point.x, point.y, 4.5, 0, Math.PI * 2); context.fill(); context.font = 'bold 11px sans-serif'; context.fillText(`N${id}`, point.x + 6, point.y - 6); });
      context.restore();
    }
    const shownNodes = nodes().map(node => ({node, point: view.project(state.draggingNode === node.id && state.preview ? state.preview : node)})).sort((a, b) => a.point.depth - b.point.depth);
    shownNodes.forEach(({node, point}) => {
      const selected = node.id === state.selectedNode, dragging = node.id === state.draggingNode;
      context.fillStyle = dragging ? '#1cb5ad' : selected ? '#ec941c' : '#e7f0fa'; context.beginPath(); context.arc(point.x, point.y, selected || dragging ? 7 : 5, 0, Math.PI * 2); context.fill(); context.strokeStyle = '#173c66'; context.lineWidth = 1.4; context.stroke();
      if (document.querySelector('#builderNodeLabels').checked) { context.fillStyle = '#183a61'; context.font = 'bold 12px sans-serif'; context.fillText(`N${node.id}`, point.x + 8, point.y - 8); }
    });
    // Abaqus 风格的边界条件标记：蓝色三角支座和已指定的自由度标签。
    shownNodes.forEach(({node, point}) => {
      const row = boundaryRow(node.id); if (!row) return;
      const fixed = boundaryFields.filter(field => row[field] !== undefined && row[field] !== null && row[field] !== ''); if (!fixed.length) return;
      context.fillStyle = '#1b63b5'; context.strokeStyle = '#0e3d78'; context.lineWidth = 1;
      context.beginPath(); context.moveTo(point.x - 8, point.y + 13); context.lineTo(point.x + 8, point.y + 13); context.lineTo(point.x, point.y + 3); context.closePath(); context.fill(); context.stroke();
      context.fillStyle = '#0e4d8d'; context.font = '11px sans-serif'; context.fillText(`BC ${fixed.map(field => ({ux: 'U1', uy: 'U2', uz: 'U3', rx: 'UR1', ry: 'UR2', rz: 'UR3'})[field]).join(',')}`, point.x + 10, point.y + 16);
    });
    window.FrameCAEModelView.drawModelLoads(context, data, view.project, width, height);
    if (state.draggingNode && state.preview) { const candidate = view.project(snap(state.preview)); context.strokeStyle = '#16a8a1'; context.lineWidth = 2; context.beginPath(); context.arc(candidate.x, candidate.y, 10, 0, Math.PI * 2); context.stroke(); }
    context.fillStyle = '#50647b'; context.font = '12px sans-serif'; context.fillText(`网格间距 ${step.toFixed(2)} m；节点 ${nodes().length} 个；杆件 ${elements().length} 根`, 12, 20);
  };
  const redrawTables = () => { markModelDirty(); renderTables(); refreshConstraintOptions(); draw(); updateSelection(); };
  const undo = () => {
    if (!history.length) { status('当前没有可以撤回的图形建模操作。'); return; }
    data = JSON.parse(history.pop());
    state.selectedNode = null; state.selectedElement = null; state.draggingNode = null; state.preview = null;
    redrawTables(); updateUndoButton(); status('已撤回上一步图形建模操作。');
  };
  const confirmModel = async () => {
    const errorBox = document.querySelector('#error'); errorBox.style.display = 'none';
    status('正在以当前自建结构求解，并更新右侧大屏…');
    document.querySelector('#status').textContent = '正在确认当前结构并进行整体刚架求解…';
    // 清除旧演示结果，避免求解失败时仍错误展示默认算例。
    const pendingPayload = editablePayload();
    document.querySelector('#builderConfirmModel').disabled = true;
    result = null; localResult = null; convergenceResult = null; displayMode = 'global'; confirmedPayload = null;
    try {
      await solve();
      if (!result) throw Error(errorBox.textContent.trim() || '当前结构未能完成求解，请查看后台日志。');
      if (JSON.stringify(editablePayload()) !== JSON.stringify(pendingPayload)) throw Error('计算期间模型已修改，请重新确认并计算。');
      confirmedPayload = JSON.parse(JSON.stringify(pendingPayload)); state.confirmed = true; setConfirmButton();
      const message = `当前自建结构已确认：${data.nodes?.length || 0} 个节点、${data.elements?.length || 0} 根杆件。右侧大屏及后续强度、局部实体、稳定分析均以该结构为参照。`;
      status(message); document.querySelector('#results').textContent += `\n\n${message}`;
    } catch (caught) { state.confirmed = false; setConfirmButton(); errorBox.textContent = caught.message; errorBox.style.display = 'block'; status('整体计算未完成，请查看错误提示。'); document.querySelector('#status').textContent = '整体计算失败，请查看错误提示。'; }
    finally { document.querySelector('#builderConfirmModel').disabled = false; window.dispatchEvent(new CustomEvent('framecae:model-state')); }
  };
  window.frameCAEConfirmModel = confirmModel;
  const newBeam = () => {
    if (!(data.materials || []).length || !(data.sections || []).length) { status('请先在材料表和截面表中至少各创建一项，再新建杆件。'); return; }
    recordHistory();
    data.nodes ||= []; data.elements ||= [];
    const step = gridStep(), existing = nodes(), selected = state.selectedNode === null ? null : nodeMap().get(state.selectedNode);
    let start = selected || existing[0], end;
    if (!start) {
      const startId = nextId(data.nodes); start = {id: startId, x: 0, y: 0, z: 0}; end = {id: startId + 1, x: step, y: 0, z: 0}; data.nodes.push(start, end);
    } else {
      const candidates = [[step, 0, 0], [0, step, 0], [0, 0, step], [-step, 0, 0], [0, -step, 0], [0, 0, -step]].map(([x, y, z]) => ({x: start.x + x, y: start.y + y, z: start.z + z}));
      const position = candidates.find(candidate => !existing.some(node => samePoint(node, candidate))) || {x: start.x + step, y: start.y, z: start.z};
      end = {id: nextId(data.nodes), ...position}; data.nodes.push(end);
    }
    const material = data.materials[0].id, section = data.sections[0].id, element = {id: nextId(data.elements), start: start.id, end: end.id, material, section};
    data.elements.push(element); state.selectedNode = end.id; state.selectedElement = element.id; status(`已创建 E${element.id}：N${start.id} → N${end.id}；默认材料 ${material}，截面 ${section}。`); redrawTables();
  };
  const removeElements = ids => {
    const removed = new Set(ids); data.elements = (data.elements || []).filter(item => !removed.has(Number(item.id)));
    data.memberLoads = (data.memberLoads || []).filter(item => !removed.has(Number(item.element)));
    data.temperatures = (data.temperatures || []).filter(item => !removed.has(Number(item.element)));
    data.assemblyDeviations = (data.assemblyDeviations || []).filter(item => !removed.has(Number(item.element)));
  };
  const deleteSelectedBeam = () => {
    if (state.selectedElement === null) { status('请先点击选择一根杆件。'); return; }
    const id = state.selectedElement; recordHistory(); removeElements([id]); state.selectedElement = null; status(`已删除 E${id}。孤立节点已保留，可按需继续连接或删除。`); redrawTables();
  };
  const deleteSelectedNode = () => {
    if (state.selectedNode === null) { status('请先点击选择一个节点。'); return; }
    const id = state.selectedNode, linked = elements().filter(item => item.start === id || item.end === id).map(item => item.id);
    if (linked.length && !window.confirm(`删除 N${id} 将同时删除相连杆件 ${linked.map(value => `E${value}`).join('、')}。是否继续？`)) return;
    recordHistory(); removeElements(linked); data.nodes = (data.nodes || []).filter(item => Number(item.id) !== id); data.loads = (data.loads || []).filter(item => Number(item.node) !== id); data.constraints = (data.constraints || []).filter(item => Number(item.node) !== id);
    state.selectedNode = null; state.selectedElement = null; status(`已删除 N${id}${linked.length ? ` 及 ${linked.length} 根相连杆件` : ''}。`); redrawTables();
  };
  const clearModel = () => {
    if (!window.confirm('将清空节点、杆件、荷载、支座、温差、杆件荷载和装配偏差；材料与截面表会保留。是否继续？')) return;
    recordHistory(); ['nodes', 'elements', 'loads', 'constraints', 'temperatures', 'memberLoads', 'assemblyDeviations'].forEach(key => { data[key] = []; }); state.selectedNode = null; state.selectedElement = null; status('图形模型已清空；材料和截面表已保留。'); redrawTables();
  };
  const elementById = id => elements().find(item => item.id === Number(id));
  const updateNodeCoordinate = (nodeId, point) => {
    const row = (data.nodes || []).find(item => Number(item.id) === Number(nodeId));
    if (!row) throw Error(`节点 N${nodeId} 不存在。`);
    Object.assign(row, point);
  };
  const relationPair = () => {
    const first = elementById(document.querySelector('#builderConstraintA').value), second = elementById(document.querySelector('#builderConstraintB').value);
    if (!first || !second) throw Error('请先创建至少两根杆件，再设置几何约束。');
    if (first.id === second.id) throw Error('基准杆和调整杆必须是两根不同的杆件。');
    const byId = nodeMap(), a0 = byId.get(first.start), a1 = byId.get(first.end), b0 = byId.get(second.start), b1 = byId.get(second.end);
    if (!a0 || !a1 || !b0 || !b1) throw Error('所选杆件端点不存在。');
    return {first, second, a0, a1, b0, b1};
  };
  const setDirectionConstraint = perpendicular => {
    try {
      const {first, second, a0, a1, b0, b1} = relationPair();
      const reference = {x: a1.x - a0.x, y: a1.y - a0.y, z: a1.z - a0.z};
      const current = {x: b1.x - b0.x, y: b1.y - b0.y, z: b1.z - b0.z};
      const refLength = Math.hypot(reference.x, reference.y, reference.z), length = Math.hypot(current.x, current.y, current.z);
      if (refLength < 1e-10 || length < 1e-10) throw Error('零长度杆件不能设置几何约束。');
      const unit = {x: reference.x / refLength, y: reference.y / refLength, z: reference.z / refLength};
      let direction;
      if (!perpendicular) {
        const sign = reference.x * current.x + reference.y * current.y + reference.z * current.z >= 0 ? 1 : -1;
        direction = {x: sign * unit.x, y: sign * unit.y, z: sign * unit.z};
      } else {
        const dot = current.x * unit.x + current.y * unit.y + current.z * unit.z;
        direction = {x: current.x - dot * unit.x, y: current.y - dot * unit.y, z: current.z - dot * unit.z};
        let normal = Math.hypot(direction.x, direction.y, direction.z);
        if (normal < 1e-10) {
          const axis = Math.abs(unit.z) < .85 ? {x: 0, y: 0, z: 1} : {x: 0, y: 1, z: 0};
          direction = {x: unit.y * axis.z - unit.z * axis.y, y: unit.z * axis.x - unit.x * axis.z, z: unit.x * axis.y - unit.y * axis.x}; normal = Math.hypot(direction.x, direction.y, direction.z);
        }
        direction = {x: direction.x / normal, y: direction.y / normal, z: direction.z / normal};
      }
      recordHistory(); updateNodeCoordinate(second.end, {x: b0.x + length * direction.x, y: b0.y + length * direction.y, z: b0.z + length * direction.z});
      state.selectedElement = second.id; state.selectedNode = null;
      status(`E${second.id} 已调整为与 E${first.id}${perpendicular ? ' 垂直' : ' 平行'}；保持 E${second.id} 原长度。`); redrawTables();
    } catch (caught) { status(caught.message); }
  };
  const mergeNodeInto = (fromId, toId) => {
    if (fromId === toId) return false;
    const linked = elements().filter(item => item.start === fromId || item.end === fromId);
    if (linked.some(item => (item.start === fromId ? item.end : item.start) === toId)) throw Error('端点重合会使一根杆件两端变为同一节点，不能生成零长度杆件。');
    (data.elements || []).forEach(item => { if (Number(item.start) === fromId) item.start = toId; if (Number(item.end) === fromId) item.end = toId; });
    data.nodes = (data.nodes || []).filter(item => Number(item.id) !== fromId);
    data.loads = (data.loads || []).map(item => Number(item.node) === fromId ? {...item, node: toId} : item);
    data.constraints = (data.constraints || []).map(item => Number(item.node) === fromId ? {...item, node: toId} : item);
    return true;
  };
  const makeCoincident = () => {
    try {
      const {first, second} = relationPair(), firstEnd = document.querySelector('#builderCoincidentA').value, secondEnd = document.querySelector('#builderCoincidentB').value;
      const fixedNode = firstEnd === 'start' ? first.start : first.end, movingNode = secondEnd === 'start' ? second.start : second.end;
      if (movingNode === fixedNode) { status('两个端点本来就是同一个节点。'); return; }
      const linked = elements().filter(item => item.start === movingNode || item.end === movingNode);
      if (linked.some(item => (item.start === movingNode ? item.end : item.start) === fixedNode)) throw Error('端点重合会使一根杆件两端变为同一节点，不能生成零长度杆件。');
      recordHistory(); mergeNodeInto(movingNode, fixedNode);
      state.selectedNode = fixedNode; state.selectedElement = null; status(`E${second.id} 的 ${secondEnd === 'start' ? '起点' : '终点'}已与 E${first.id} 的${firstEnd === 'start' ? '起点' : '终点'}重合，并合并为 N${fixedNode}。`); redrawTables();
    } catch (caught) { status(caught.message); }
  };
  const applyBoundaryCondition = () => {
    const nodeId = state.selectedNode;
    if (nodeId === null) { status('请先在画布中选中一个节点，再创建边界条件。'); return; }
    const values = Object.fromEntries(boundaryFields.map(field => [field, {checked: document.querySelector(`[data-bc="${field}"]`).checked, value: Number(document.querySelector(`[data-bc-value="${field}"]`).value)}]));
    if (Object.values(values).some(item => item.checked && !Number.isFinite(item.value))) { status('已指定的位移或转角值必须是有限数字。'); return; }
    recordHistory(); data.constraints ||= [];
    let row = boundaryRow(nodeId); if (!row) { row = {node: nodeId}; data.constraints.push(row); }
    boundaryFields.forEach(field => { if (values[field].checked) row[field] = values[field].value; else delete row[field]; });
    if (!boundaryFields.some(field => row[field] !== undefined)) data.constraints = data.constraints.filter(item => item !== row);
    status(`N${nodeId} 的位移／转角边界条件已更新。蓝色支座符号表示已指定自由度。`); redrawTables(); refreshBoundaryControls();
  };
  const clearBoundaryCondition = () => {
    const nodeId = state.selectedNode, row = nodeId === null ? null : boundaryRow(nodeId);
    if (!row) { status('当前节点没有可清除的边界条件。'); return; }
    recordHistory(); data.constraints = data.constraints.filter(item => item !== row); status(`已清除 N${nodeId} 的边界条件。`); redrawTables(); refreshBoundaryControls();
  };
  const applyNodeLoad = () => {
    const nodeId = state.selectedNode;
    if (nodeId === null) { status('请先在画布中选中一个节点，再创建节点荷载。'); return; }
    const values = Object.fromEntries(loadFields.map(field => [field, Number(document.querySelector(`[data-load="${field}"]`).value)]));
    if (Object.values(values).some(value => !Number.isFinite(value))) { status('荷载分量必须是有限数字。'); return; }
    recordHistory(); data.loads ||= [];
    let row = loadRow(nodeId); if (!row) { row = {node: nodeId}; data.loads.push(row); }
    Object.assign(row, values);
    if (loadFields.every(field => values[field] === 0)) data.loads = data.loads.filter(item => item !== row);
    status(`N${nodeId} 的集中力／力矩已更新。红色箭头表示非零集中力方向。`); redrawTables(); refreshLoadControls();
  };
  const clearNodeLoad = () => {
    const nodeId = state.selectedNode, row = nodeId === null ? null : loadRow(nodeId);
    if (!row) { status('当前节点没有可清除的节点荷载。'); return; }
    recordHistory(); data.loads = data.loads.filter(item => item !== row); status(`已清除 N${nodeId} 的节点荷载。`); redrawTables(); refreshLoadControls();
  };
  const commitDrag = () => {
    const id = state.draggingNode; if (id === null || !state.preview) return;
    const original = nodeMap().get(id), target = snap(state.preview), linked = elements().filter(item => item.start === id || item.end === id);
    if (original && samePoint(original, target)) { state.preview = null; state.draggingNode = null; draw(); return; }
    const match = nodes().find(node => node.id !== id && samePoint(node, target));
    const otherEndSame = linked.some(item => (item.start === id ? item.end : item.start) === (match ? match.id : -1));
    if (match && otherEndSame) { status(`N${id} 不能吸附到 N${match.id}：这会生成零长度杆件。`); state.preview = null; state.draggingNode = null; draw(); return; }
    recordHistory();
    if (match) {
      (data.elements || []).forEach(item => { if (Number(item.start) === id) item.start = match.id; if (Number(item.end) === id) item.end = match.id; });
      data.nodes = (data.nodes || []).filter(item => Number(item.id) !== id); data.loads = (data.loads || []).map(item => Number(item.node) === id ? {...item, node: match.id} : item); data.constraints = (data.constraints || []).map(item => Number(item.node) === id ? {...item, node: match.id} : item);
      state.selectedNode = match.id; status(`N${id} 已吸附并合并至 N${match.id}：(${target.x.toFixed(3)}, ${target.y.toFixed(3)}, ${target.z.toFixed(3)}) m。`);
    } else if (original) {
      const row = (data.nodes || []).find(item => Number(item.id) === id); Object.assign(row, target); state.selectedNode = id; status(`N${id} 已吸附至 (${target.x.toFixed(3)}, ${target.y.toFixed(3)}, ${target.z.toFixed(3)}) m。`);
    }
    state.preview = null; state.draggingNode = null; redrawTables();
  };
  const pointer = event => { const box = canvas.getBoundingClientRect(); return {x: event.clientX - box.left, y: event.clientY - box.top}; };
  canvas.addEventListener('pointerdown', event => {
    const point = pointer(event), view = projection(), hitNode = nodes().map(node => ({node, point: view.project(node)})).sort((a, b) => Math.hypot(a.point.x - point.x, a.point.y - point.y) - Math.hypot(b.point.x - point.x, b.point.y - point.y))[0];
    if (hitNode && Math.hypot(hitNode.point.x - point.x, hitNode.point.y - point.y) < 11) {
      state.selectedNode = hitNode.node.id; state.selectedElement = null; state.draggingNode = hitNode.node.id; state.preview = {...hitNode.node}; state.cameraDrag = {x: event.clientX, y: event.clientY, origin: {...hitNode.node}, view}; state.moved = false; wrap.classList.add('drag-node'); canvas.setPointerCapture(event.pointerId); updateSelection(); draw(); return;
    }
    const byId = nodeMap(), hitElement = elements().map(element => ({element, first: view.project(byId.get(element.start)), second: view.project(byId.get(element.end))})).filter(item => item.first && item.second).sort((a, b) => distanceToSegment(point, a.first, a.second) - distanceToSegment(point, b.first, b.second))[0];
    if (hitElement && distanceToSegment(point, hitElement.first, hitElement.second) < 8) { state.selectedElement = hitElement.element.id; state.selectedNode = null; state.cameraDrag = null; refreshConstraintOptions(); document.querySelector('#builderConstraintA').value = String(hitElement.element.id); updateSelection(); draw(); return; }
    state.selectedNode = null; state.selectedElement = null; state.cameraDrag = {x: event.clientX, y: event.clientY}; state.moved = false; updateSelection(); canvas.setPointerCapture(event.pointerId); draw();
  });
  canvas.addEventListener('pointermove', event => {
    if (!state.cameraDrag) return;
    const dx = event.clientX - state.cameraDrag.x, dy = event.clientY - state.cameraDrag.y;
    if (state.draggingNode !== null) {
      const {origin, view} = state.cameraDrag, amountX = dx / view.pixels, amountY = -dy / view.pixels;
      state.preview = {x: origin.x + amountX * view.horizontal.x + amountY * view.vertical.x, y: origin.y + amountX * view.horizontal.y + amountY * view.vertical.y, z: origin.z + amountX * view.horizontal.z + amountY * view.vertical.z}; state.moved ||= Math.hypot(dx, dy) > 2; draw();
    } else { state.yaw += dx * .008; state.pitch = Math.max(-1.45, Math.min(1.45, state.pitch + dy * .008)); state.cameraDrag.x = event.clientX; state.cameraDrag.y = event.clientY; state.moved = true; draw(); }
  });
  const finishPointer = event => {
    if (state.draggingNode !== null) {
      if (state.moved) commitDrag();
      else { state.draggingNode = null; state.preview = null; draw(); }
    }
    state.cameraDrag = null; state.moved = false; wrap.classList.remove('drag-node'); if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  };
  canvas.addEventListener('pointerup', finishPointer); canvas.addEventListener('pointercancel', finishPointer);
  canvas.addEventListener('wheel', event => { event.preventDefault(); state.zoom = Math.max(.25, Math.min(5, state.zoom * (event.deltaY < 0 ? 1.12 : .89))); draw(); }, {passive: false});
  document.querySelector('#builderNewBeam').onclick = newBeam; document.querySelector('#builderConfirmModel').onclick = confirmModel; document.querySelector('#builderUndo').onclick = undo; document.querySelector('#builderDeleteBeam').onclick = deleteSelectedBeam; document.querySelector('#builderDeleteNode').onclick = deleteSelectedNode; document.querySelector('#builderClear').onclick = clearModel;
  document.querySelector('#builderParallel').onclick = () => setDirectionConstraint(false); document.querySelector('#builderPerpendicular').onclick = () => setDirectionConstraint(true); document.querySelector('#builderCoincident').onclick = makeCoincident;
  document.querySelector('#builderApplyBC').onclick = applyBoundaryCondition; document.querySelector('#builderClearBC').onclick = clearBoundaryCondition;
  document.querySelector('#builderApplyLoad').onclick = applyNodeLoad; document.querySelector('#builderClearLoad').onclick = clearNodeLoad;
  document.querySelectorAll('[data-bc]').forEach(check => check.onchange = () => { document.querySelector(`[data-bc-value="${check.dataset.bc}"]`).disabled = !check.checked; });
  ['#runStrengthCheck', '#runStabilityCheck', '#runLocal', '#runConvergence', '#runGeneric', '#runGenericConvergence', '#autoT', '#selectedT', '#autoGeneric', '#selectedGeneric'].forEach(selector => document.querySelector(selector)?.addEventListener('click', requireConfirmedModel, true));
  document.querySelector('#builderResetView').onclick = () => { state.yaw = -.72; state.pitch = .50; state.zoom = 1; draw(); };
  ['#builderGridStep', '#builderGridVisible', '#builderNodeLabels', '#builderElementLabels'].forEach(selector => document.querySelector(selector).addEventListener('input', draw));
  const rawMakeRow = makeRow;
  makeRow = function (name, schema, row, index) {
    const tr = rawMakeRow(name, schema, row, index);
    if (name !== 'nodes') return tr;
    const input = tr.querySelector('input'), previous = Number(row.id);
    input.setAttribute('aria-label', window.FrameCAEModelView.nodeLabel(previous) + ' 节点号');
    // Commit the identity and all references together after editing, never use
    // table position as the node identity or leave forces attached to an old ID.
    input.oninput = () => {};
    input.onchange = () => {
      const next = Number(input.value);
      if (next === previous) return;
      try {
        const copy = JSON.parse(JSON.stringify(data));
        window.FrameCAEModelView.renameNode(copy, previous, next);
        recordHistory();data = copy;
        if (state.selectedNode === previous) state.selectedNode = next;
        for (const id of ['localNode','genericNode']) {
          const select = document.querySelector('#'+id);
          if (Number(select.value) === previous) select.dataset.renamedNode = String(next);
        }
        redrawTables();status(`节点已统一更新：N${previous} → N${next}；杆件端点、支座和荷载同步更新，请重新确认并计算。`);
      } catch (error) { input.value = previous;status(error.message); }
    };
    return tr;
  };
  refreshLocalNodeOptions = function () {
    const model = payload();
    for (const id of ['localNode','genericNode']) {
      const select = document.querySelector('#'+id), selected = select.dataset.renamedNode || select.value;
      select.replaceChildren(...(model.nodes || []).map(node => new Option(window.FrameCAEModelView.nodeLabel(node.id), String(node.id))));
      if ([...select.options].some(option => option.value === selected)) select.value = selected;
      delete select.dataset.renamedNode;
    }
  };
  const rawRenderTables = renderTables;
  renderTables = function () { rawRenderTables(); draw(); updateSelection(); };
  tables.addEventListener('input', () => { markModelDirty(); window.requestAnimationFrame(draw); });
  tables.addEventListener('click', event => { if(event.target.closest('button')) markModelDirty(); });
  ['#selfWeightSettings','#assemblySettings'].forEach(selector => {
    const panel=document.querySelector(selector);
    panel?.addEventListener('input', markModelDirty);panel?.addEventListener('change', markModelDirty);
    panel?.addEventListener('click', event => {if(event.target.closest('button')) markModelDirty();});
  });
  const rawLoadDefault = loadDefault;
  loadDefault = async () => { await rawLoadDefault(); confirmedPayload = null; history.length = 0; state.confirmed = false; setConfirmButton(); updateUndoButton(); refreshConstraintOptions(); draw(); updateSelection(); };
  const rawImport = importModel;
  importModel = file => { rawImport(file); window.setTimeout(() => { confirmedPayload = null; history.length = 0; state.confirmed = false; setConfirmButton(); updateUndoButton(); state.selectedNode = null; state.selectedElement = null; refreshConstraintOptions(); draw(); updateSelection(); }, 80); };
  // AI 只通过这个受控桥接访问基准版画布。用户已在每次生成前确认材料和截面，
  // 应用时将它们与节点、杆件、荷载、约束一并写入；其他设置保留。
  window.frameCAEModelAssistant = {
    currentModel: () => JSON.parse(JSON.stringify(editablePayload())),
    preview: draft => {
      if (!draft?.model?.nodes || !draft?.model?.elements) throw Error('AI 草案格式不完整，无法预览。');
      state.aiDraft = JSON.parse(JSON.stringify(draft));
      const suggested = Number(draft.recommendedGridStep);
      if (Number.isFinite(suggested) && suggested >= 0.05) document.querySelector('#builderGridStep').value = suggested.toFixed(2);
      draw(); status(`正在预览 AI 草案：${draft.summary?.nodeCount ?? draft.model.nodes.length} 个节点、${draft.summary?.elementCount ?? draft.model.elements.length} 根杆件。紫色虚线尚未写入当前模型。`);
    },
    clearPreview: () => { state.aiDraft = null; draw(); },
    apply: draft => {
      if (!draft?.model?.nodes || !draft?.model?.elements) throw Error('AI 草案格式不完整，无法应用。');
      if (!draft.model.materials?.length || !draft.model.sections?.length) throw Error('草案缺少已确认的材料或截面，无法应用。');
      recordHistory(); ['materials', 'sections', 'nodes', 'elements', 'loads', 'constraints', 'memberLoads', 'temperatures', 'assemblyDeviations'].forEach(key => { data[key] = JSON.parse(JSON.stringify(draft.model[key] || [])); });
      state.aiDraft = null; state.selectedNode = null; state.selectedElement = null; state.confirmed = false; confirmedPayload = null;
      result = null; localResult = null; convergenceResult = null; displayMode = 'global'; setConfirmButton(); redrawTables();
      const suggested = Number(draft.recommendedGridStep);
      if (Number.isFinite(suggested) && suggested >= 0.05) document.querySelector('#builderGridStep').value = suggested.toFixed(2);
      draw(); status(`已将 AI 草案写入图表：${data.nodes.length} 个节点、${data.elements.length} 根杆件。请核对后确认并求解。`);
    },
  };
  // Manual modeling helpers use the same history, invalidation and redraw path.
  window.frameCAEManualBuilder = {
    fitView: () => {
      const list=nodes();if(!list.length)return;
      const span=Math.max(...['x','y','z'].map(a=>Math.max(...list.map(n=>n[a]))-Math.min(...list.map(n=>n[a]))),.01);
      state.zoom=Math.min(5,Math.max(.25,centerAndScale().range/span*1.6));draw();
    },
    snapshot: () => ({nodes:nodes(), selectedNode:state.selectedNode, materials:data.materials||[], sections:data.sections||[]}),
    selectNode: id => {
      const n = id === '' ? null : nodeMap().get(Number(id));
      state.selectedNode=n?.id??null;state.selectedElement=null;updateSelection();draw();
    },
    prepareTube: ({diameter,thickness,elasticModulus}) => {
      if ((data.materials||[]).length && (data.sections||[]).length) return;
      const d=Number(diameter)/1000,t=Number(thickness)/1000,e=Number(elasticModulus);
      if (![d,t,e].every(Number.isFinite)||d<=0||t<=0||2*t>=d||e<=0) {status('请输入有效参数：外径、壁厚、弹性模量均为正，且壁厚小于外径的一半。');return;}
      recordHistory();data.materials ||= [];data.sections ||= [];
      if (!data.materials.length)data.materials.push({id:1,e,nu:.3,alpha:12,density:7850});
      if (!data.sections.length){const inner=d-2*t,a=Math.PI*(d*d-inner*inner)/4,i=Math.PI*(d**4-inner**4)/64;data.sections.push({id:1,a,iy:i,iz:i,j:2*i,d});}
      redrawTables();status('钢材与圆管截面已设置。详细参数可在“参数表格”中修改。');
    },
    addDirected: ({direction,length,endNode,endPosition,material,section}) => {
      const mat=(data.materials||[]).find(m=>Number(m.id)===Number(material)),sec=(data.sections||[]).find(s=>Number(s.id)===Number(section));
      if (!mat||!sec){status('请先设置材料与截面。');return;}
      const existing=nodes(),selected=nodeMap().get(state.selectedNode);
      if(existing.length&&!selected){status('请先选择起点节点。');return;}
      const start=selected||{id:nextId(data.nodes||[]),x:0,y:0,z:0};
      const vectors={xp:[1,0,0],xn:[-1,0,0],yp:[0,1,0],yn:[0,-1,0],zp:[0,0,1],zn:[0,0,-1]};
      let end;
      if(endNode==='coordinates'){
        if(!endPosition||!['x','y','z'].every(k=>String(endPosition[k]??'').trim()!==''&&Number.isFinite(Number(endPosition[k])))){status('请填写完整、有效的终点 X、Y、Z 坐标。');return;}
        const p=Object.fromEntries(['x','y','z'].map(k=>[k,Number(endPosition[k])]));
        end=existing.find(n=>samePoint(n,p))||{id:Math.max(nextId(data.nodes||[]),start.id+1),...p};
      }
      else if(endNode){end=nodeMap().get(Number(endNode));if(!end){status('目标节点不存在，请重新选择。');return;}}
      else {const l=Number(length),v=vectors[direction];if(!v||!Number.isFinite(l)||l<=0){status('杆长必须是大于 0 的有限数字。');return;}const p={x:start.x+l*v[0],y:start.y+l*v[1],z:start.z+l*v[2]};end=existing.find(n=>samePoint(n,p))||{id:Math.max(nextId(data.nodes||[]),start.id+1),...p};}
      if(samePoint(start,end)){status('起点与终点重合，不能创建零长度杆件。');return;}
      if(elements().some(e=>(e.start===start.id&&e.end===end.id)||(e.start===end.id&&e.end===start.id))){status('这两个节点之间已有杆件，无需重复添加。');return;}
      recordHistory();data.nodes ||= [];data.elements ||= [];
      if(!existing.some(n=>n.id===start.id))data.nodes.push(start);
      if(!existing.some(n=>n.id===end.id))data.nodes.push(end);
      const element={id:nextId(data.elements),start:start.id,end:end.id,material:mat.id,section:sec.id};data.elements.push(element);
      state.selectedNode=end.id;state.selectedElement=element.id;redrawTables();
      status(`已添加 E${element.id}：N${start.id} → N${end.id}；已选中终点，可继续接下一根杆。`);
    },
  };

  window.addEventListener('framecae:loads-updated', () => requestAnimationFrame(draw));
  window.frameCAERefreshVisualBuilder = () => { refreshConstraintOptions(); refreshBoundaryControls(); refreshLoadControls(); draw(); updateSelection(); };
  setConfirmButton(); new ResizeObserver(draw).observe(canvas); window.setTimeout(() => { refreshConstraintOptions(); refreshBoundaryControls(); refreshLoadControls(); draw(); }, 30); window.setTimeout(() => { refreshConstraintOptions(); refreshBoundaryControls(); refreshLoadControls(); draw(); }, 600);
})();
