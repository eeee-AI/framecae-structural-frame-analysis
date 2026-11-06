(() => {
const workspaceHost = document.getElementById('calibratedImageWorkspace');
const workspaceRoot = workspaceHost?.shadowRoot || document;
const $ = (id) => workspaceRoot.getElementById(id);
const state = {
  images: [], tracks: [], nextId: 1, selectedId: null,
  calibration: null, result: null,
  rodCandidates: [], selectedRods: new Set(), highlightedRod: null,
  yaw: 0.7, pitch: -0.35, viewerZoom: 1,
};

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function notify(message, success = false) {
  const el = $('notice');
  el.textContent = message;
  el.className = `notice${success ? ' success' : ''}`;
  el.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

function clearNotice() { $('notice').className = 'notice hidden'; }
function selectedTrack() { return state.tracks.find((t) => t.id === state.selectedId); }
function activeTracks() { return state.tracks.filter((t) => Object.keys(t.observations).length); }
function invalidateResult() {
  state.result = null;
  state.rodCandidates = [];
  state.selectedRods = new Set();
  state.highlightedRod = null;
  $('sendToFrameCAEBtn').disabled = true;
  $('resultSection').classList.add('hidden');
  $('candidateList').innerHTML = '';
  $('rodPreviews').innerHTML = '';
  renderRodOverlays();
}

function addTrack() {
  if (state.tracks.length >= 100) return notify('最多支持 100 组对应点。');
  const id = String(state.nextId++);
  state.tracks.push({id, label: `P${id}`, observations: {}});
  state.selectedId = id;
  renderTracks();
  updateGuide();
  renderMarkers();
}

function ensureTrack() { if (!selectedTrack()) addTrack(); }

function updateGuide() {
  const track = selectedTrack();
  $('activeTrack').textContent = track ? track.label : '—';
  if (!state.images.length) {
    $('nextStep').textContent = '上传照片后，点击第 1 张图上的目标位置。';
    return;
  }
  if (!track) {
    $('nextStep').textContent = '新建点组后，依次点击各照片上的同一位置。';
    return;
  }
  const missing = state.images.findIndex((_, index) => !track.observations[index]);
  $('nextStep').textContent = missing < 0
    ? `${track.label} 已在所有照片标注。可新建点组。`
    : `正在标注 ${track.label}：请点击第 ${missing + 1} 张照片上的同一物理点。`;
}

function renderTracks() {
  $('trackCount').textContent = activeTracks().length;
  const holder = $('trackList');
  holder.innerHTML = '';
  for (const track of state.tracks) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `track-chip${track.id === state.selectedId ? ' active' : ''}`;
    const marks = state.images.map((_, index) => track.observations[index] ? `<b>${index + 1}</b>` : '·').join(' ');
    chip.innerHTML = `<span class="chip-name">${escapeHTML(track.label)}</span><span class="chip-presence">${marks}</span>`;
    chip.title = '选择这个编号，继续标注或修正点位';
    chip.addEventListener('click', () => {
      state.selectedId = track.id;
      renderTracks(); renderMarkers(); updateGuide();
    });
    holder.append(chip);
  }
  renderScaleOptions();
}

function renderScaleOptions() {
  for (const id of ['scaleA', 'scaleB']) {
    const select = $(id);
    const previous = select.value;
    select.innerHTML = '<option value="">不指定</option>';
    for (const track of activeTracks()) {
      const option = document.createElement('option');
      option.value = track.id;
      option.textContent = track.label;
      select.append(option);
    }
    select.value = [...select.options].some((option) => option.value === previous) ? previous : '';
  }
}

function renderMarkers() {
  workspaceRoot.querySelectorAll('.marker-layer').forEach((layer) => {
    const index = Number(layer.dataset.viewIndex);
    layer.innerHTML = '';
    for (const track of state.tracks) {
      const point = track.observations[index];
      if (!point) continue;
      const marker = document.createElement('div');
      marker.className = `marker${track.id === state.selectedId ? ' active' : ''}`;
      marker.style.left = `${100 * point[0] / state.images[index].width}%`;
      marker.style.top = `${100 * point[1] / state.images[index].height}%`;
      marker.textContent = track.label;
      layer.append(marker);
    }
  });
}

function renderGallery() {
  const grid = $('imageGrid');
  grid.innerHTML = '';
  if (!state.images.length) {
    grid.classList.add('empty-grid');
    grid.innerHTML = '<div class="empty-state">照片会显示在这里。每张图都可以独立放大，点击可重新设置当前点位。</div>';
    return;
  }
  grid.classList.remove('empty-grid');
  state.images.forEach((image, index) => {
    const card = document.createElement('article');
    card.className = 'image-card';
    card.innerHTML = `
      <div class="image-card-head">
        <div class="image-title"><span class="image-index">${index + 1}</span><span class="image-filename" title="${escapeHTML(image.name)}">${escapeHTML(image.name)}</span></div>
        <div class="image-order"><button type="button" class="move-left" title="向前移动" ${index === 0 ? 'disabled' : ''}>←</button><button type="button" class="move-right" title="向后移动" ${index === state.images.length - 1 ? 'disabled' : ''}>→</button></div>
      </div>
      <div class="image-stage"><div class="image-shell"><img draggable="false" alt="视图 ${index + 1}"><svg class="rod-layer" data-view-index="${index}"></svg><div class="marker-layer" data-view-index="${index}"></div></div></div>
      <div class="image-card-foot"><label>放大 <input class="zoom-slider" type="range" min="1" max="5" step="0.25" value="${image.zoom}"></label><span class="zoom-text">${image.zoom.toFixed(2)}×</span><span class="image-size">${image.width} × ${image.height}</span></div>`;
    const img = card.querySelector('img');
    img.src = image.url;
    const shell = card.querySelector('.image-shell');
    shell.style.width = `${image.zoom * 100}%`;
    const stage = card.querySelector('.image-stage');
    stage.addEventListener('click', (event) => {
      const rect = img.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right ||
          event.clientY < rect.top || event.clientY > rect.bottom) return;
      ensureTrack();
      const track = selectedTrack();
      track.observations[index] = [
        (event.clientX - rect.left) / rect.width * image.width,
        (event.clientY - rect.top) / rect.height * image.height,
      ];
      clearNotice(); invalidateResult(); renderMarkers(); renderTracks(); updateGuide();
      if (state.images.every((_, view) => track.observations[view]) && activeTracks().length < 7) addTrack();
    });
    const slider = card.querySelector('.zoom-slider');
    const zoomText = card.querySelector('.zoom-text');
    slider.addEventListener('input', () => {
      image.zoom = Number(slider.value);
      shell.style.width = `${image.zoom * 100}%`;
      zoomText.textContent = `${image.zoom.toFixed(2)}×`;
    });
    stage.addEventListener('wheel', (event) => {
      if (!(event.ctrlKey || event.altKey)) return;
      event.preventDefault();
      image.zoom = Math.max(1, Math.min(5, image.zoom + (event.deltaY < 0 ? 0.25 : -0.25)));
      slider.value = image.zoom;
      shell.style.width = `${image.zoom * 100}%`;
      zoomText.textContent = `${image.zoom.toFixed(2)}×`;
    }, {passive: false});
    card.querySelector('.move-left').addEventListener('click', () => moveImage(index, index - 1));
    card.querySelector('.move-right').addEventListener('click', () => moveImage(index, index + 1));
    grid.append(card);
  });
  renderMarkers();
  renderRodOverlays();
}

function moveImage(a, b) {
  if (b < 0 || b >= state.images.length) return;
  [state.images[a], state.images[b]] = [state.images[b], state.images[a]];
  for (const track of state.tracks) {
    const oldA = track.observations[a], oldB = track.observations[b];
    if (oldB) track.observations[a] = oldB; else delete track.observations[a];
    if (oldA) track.observations[b] = oldA; else delete track.observations[b];
  }
  invalidateResult(); renderGallery(); renderTracks(); updateGuide();
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({name: file.name, url, width: img.naturalWidth,
                                height: img.naturalHeight, zoom: 1});
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(`无法读取 ${file.name}`)); };
    img.src = url;
  });
}

async function handleImages(event) {
  const files = [...event.target.files];
  event.target.value = '';
  if (files.length < 2 || files.length > 4) return notify('请一次选择 2–4 张照片。');
  try {
    const images = await Promise.all(files.map(loadImage));
    const base = state.calibration?.image_size_px;
    if (base && images.some((img) => Math.abs(img.width / img.height - base[0] / base[1]) >
      0.01 * base[0] / base[1])) {
      images.forEach((img) => URL.revokeObjectURL(img.url));
      return notify('所选照片与标定图宽高比不同。请使用这台相机未经裁剪的照片。');
    }
    state.images.forEach((img) => URL.revokeObjectURL(img.url));
    state.images = images;
    state.tracks = []; state.nextId = 1; state.selectedId = null;
    invalidateResult(); clearNotice();
    $('imageCount').textContent = `${images.length} / 4`;
    addTrack(); renderGallery(); updateGuide();
  } catch (error) { notify(error.message); }
}

function removeCurrentTrack(clearOnly = false) {
  const track = selectedTrack();
  if (!track) return;
  if (clearOnly) track.observations = {};
  else {
    state.tracks = state.tracks.filter((item) => item.id !== track.id);
    state.selectedId = state.tracks.at(-1)?.id ?? null;
    if (!state.tracks.length) addTrack();
  }
  invalidateResult(); renderMarkers(); renderTracks(); updateGuide();
}

function annotationData() {
  return {
    format: 'manual-multiview-v1',
    views: state.images.map((img) => ({name: img.name, width: img.width, height: img.height})),
    tracks: activeTracks().map((track) => ({id: track.id, label: track.label,
      observations: track.observations})),
    calibration_image_size_px: state.calibration?.image_size_px,
  };
}

function downloadText(filename, content, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importAnnotations(event) {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.format !== 'manual-multiview-v1' || !Array.isArray(data.views) ||
        !Array.isArray(data.tracks)) throw new Error('不是本界面导出的标注文件。');
    if (data.views.length !== state.images.length || data.views.some((view, i) =>
      view.name !== state.images[i].name || view.width !== state.images[i].width ||
      view.height !== state.images[i].height)) {
      throw new Error('请先按原顺序上传标注文件对应的照片。');
    }
    state.tracks = data.tracks.map((track) => ({id: String(track.id),
      label: String(track.label || `P${track.id}`), observations: track.observations || {}}));
    state.nextId = Math.max(0, ...state.tracks.map((track) => Number(track.id) || 0)) + 1;
    state.selectedId = state.tracks.at(-1)?.id ?? null;
    if (!state.tracks.length) addTrack();
    invalidateResult(); renderMarkers(); renderTracks(); updateGuide();
    notify('标注已导入。', true);
  } catch (error) { notify(error.message); }
}

function scaleRequest() {
  const a = $('scaleA').value, b = $('scaleB').value, distance = $('scaleDistance').value.trim();
  if (!a && !b && !distance) return null;
  if (!a || !b || !distance || a === b) throw new Error('确定毫米尺度时，请选择两个不同点并填写实际距离。');
  if (!Number.isFinite(Number(distance)) || Number(distance) <= 0)
    throw new Error('已知距离应为大于 0 的毫米数。');
  return {point_a: a, point_b: b, distance_mm: Number(distance)};
}

async function runReconstruction() {
  try {
    if (!state.calibration) throw new Error('标定文件尚未加载。');
    if (state.images.length < 2) throw new Error('请先上传 2–4 张照片。');
    const data = annotationData();
    const firstPair = data.tracks.filter((track) => track.observations[0] && track.observations[1]);
    if (firstPair.length < 7) throw new Error('前两张照片需要全部 7 组共同对应点。');
    const scale = scaleRequest();
    $('reconstructBtn').disabled = true;
    $('runStatus').textContent = '正在估计相机位姿并联合优化…';
    clearNotice();
    const response = await fetch('/api/image-reconstruction/reconstruct', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...data, scale})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '重建失败。');
    state.result = result;
    renderResult();
    $('runStatus').textContent = `已完成：${result.points.length} 个三维点`;
    $('resultSection').scrollIntoView({behavior: 'smooth', block: 'start'});
    await runRodInference();
  } catch (error) {
    $('runStatus').textContent = '重建未完成';
    notify(error.message);
  } finally { $('reconstructBtn').disabled = false; }
}

function formatNumber(number, digits = 2) { return Number(number).toFixed(digits); }

function renderResult() {
  const result = state.result;
  $('resultSection').classList.remove('hidden');
  $('pointMetric').textContent = result.points.length;
  $('errorMetric').textContent = `${formatNumber(result.overall_rmse_px, 2)} px`;
  $('unitMetric').textContent = result.unit === 'mm' ? '毫米 mm' : '相对单位';
  $('inlierMetric').textContent = `${result.baseline_inliers} / ${result.baseline_matches}`;
  $('resultWarnings').innerHTML = result.warnings.map((warning) => `<p>⚠ ${escapeHTML(warning)}</p>`).join('');
  $('viewErrors').innerHTML = result.cameras.map((camera) =>
    `<span>视图 ${camera.view_index + 1} · ${formatNumber(result.per_view_rmse_px[camera.view_index], 2)} px</span>`).join('');
  $('pointTable').innerHTML = result.points.map((point) => `<tr><td>${escapeHTML(point.label)}</td>` +
    point.xyz.map((value) => `<td>${formatNumber(value, 3)}</td>`).join('') +
    `<td>${formatNumber(point.rmse_px, 2)}</td></tr>`).join('');
  drawViewer();
}

function drawViewer() {
  if (!state.result) return;
  const canvas = $('pointViewer');
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.fillStyle = '#132521'; ctx.fillRect(0, 0, width, height);
  const points = state.result.points.map((p) => p.xyz);
  const cameras = state.result.cameras.map((c) => c.center);
  const all = [...points, ...cameras];
  if (!all.length) return;
  const min = [0, 1, 2].map((a) => Math.min(...all.map((p) => p[a])));
  const max = [0, 1, 2].map((a) => Math.max(...all.map((p) => p[a])));
  const center = min.map((value, a) => (value + max[a]) / 2);
  const span = Math.max(1e-8, ...max.map((value, a) => value - min[a]));
  const scale = Math.min(width, height) * .68 / span * state.viewerZoom;
  const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
  const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
  function project(p) {
    const dx = p[0] - center[0], dy = p[1] - center[1], dz = p[2] - center[2];
    const rx = cy * dx + sy * dz, rz = -sy * dx + cy * dz;
    const ry = cp * dy - sp * rz, depth = sp * dy + cp * rz;
    return [width / 2 + rx * scale, height / 2 - ry * scale, depth];
  }
  const origin = project(center);
  const axisLength = span * .22;
  for (const [axis, color, letter] of [[0, '#ff8e7a', 'X'], [1, '#8fdf9c', 'Y'], [2, '#77b8ff', 'Z']]) {
    const end = center.slice(); end[axis] += axisLength;
    const pixel = project(end);
    ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(origin[0], origin[1]); ctx.lineTo(pixel[0], pixel[1]); ctx.stroke();
    ctx.fillStyle = color; ctx.font = 'bold 12px sans-serif'; ctx.fillText(letter, pixel[0] + 5, pixel[1] - 3);
  }
  const byId = Object.fromEntries(state.result.points.map((point) => [point.id, point.xyz]));
  for (const candidate of state.rodCandidates) {
    const isSelected = state.selectedRods.has(candidate.id);
    const isHighlighted = state.highlightedRod === candidate.id;
    if (!isSelected && !isHighlighted) continue;
    const a = byId[candidate.a], b = byId[candidate.b];
    if (!a || !b) continue;
    const pa = project(a), pb = project(b);
    ctx.strokeStyle = isHighlighted ? '#f4bf67' : '#7ed8b2';
    ctx.lineWidth = isHighlighted ? 5 : 3;
    ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(pa[0], pa[1]); ctx.lineTo(pb[0], pb[1]); ctx.stroke();
  }
  const scene = [
    ...state.result.points.map((item) => ({kind: 'point', label: item.label, p: project(item.xyz)})),
    ...state.result.cameras.map((item) => ({kind: 'camera', label: `C${item.view_index + 1}`, p: project(item.center)})),
  ].sort((a, b) => a.p[2] - b.p[2]);
  for (const item of scene) {
    const [x, y] = item.p;
    if (item.kind === 'camera') {
      ctx.fillStyle = '#ec9476';
      ctx.beginPath(); ctx.moveTo(x, y - 8); ctx.lineTo(x + 7, y + 6); ctx.lineTo(x - 7, y + 6); ctx.closePath(); ctx.fill();
    } else {
      ctx.fillStyle = '#b5f0ca'; ctx.shadowBlur = 10; ctx.shadowColor = '#8ddbb0';
      ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
    }
    ctx.fillStyle = '#e9f5ec'; ctx.font = '11px sans-serif'; ctx.fillText(item.label, x + 8, y - 5);
  }
  ctx.fillStyle = '#9eb6ab'; ctx.font = '12px sans-serif';
  ctx.fillText(`● 三维点   ▲ 相机位置    单位：${state.result.unit === 'mm' ? 'mm' : '相对单位'}`, 17, height - 18);
}

function analysisImage(image) {
  if (image.analysisDataUrl) return Promise.resolve(image.analysisDataUrl);
  return new Promise((resolve, reject) => {
    const source = new Image();
    source.onload = () => {
      const scale = Math.min(1, 1800 / source.naturalWidth);
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(source.naturalWidth * scale);
      canvas.height = Math.round(source.naturalHeight * scale);
      canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
      image.analysisDataUrl = canvas.toDataURL('image/jpeg', .83);
      resolve(image.analysisDataUrl);
    };
    source.onerror = () => reject(new Error(`无法压缩照片：${image.name}`));
    source.src = image.url;
  });
}

async function runRodInference() {
  if (!state.result) return;
  const button = $('inferRodsBtn');
  button.disabled = true;
  $('rodStatus').textContent = '正在分析照片中的杆件线段，并进行多视图对照…';
  try {
    const dataUrls = await Promise.all(state.images.map(analysisImage));
    const views = state.images.map((image, index) => ({
      name: image.name, width: image.width, height: image.height,
      image_data_url: dataUrls[index],
    }));
    const response = await fetch('/api/image-reconstruction/infer-rods', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({views, reconstruction: state.result})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '杆件识别失败。');
    state.rodCandidates = data.candidates;
    state.selectedRods = new Set(data.candidates.filter((item) => item.status === 'suggested').map((item) => item.id));
    state.highlightedRod = data.candidates[0]?.id ?? null;
    $('rodStatus').textContent = `已分析 ${data.candidates.length} 条候选连接；绿色为自动建议，黄色请重点复核。`;
    renderCandidateList(); renderRodOverlays(); drawViewer();
    $('rodSection').scrollIntoView({behavior: 'smooth', block: 'start'});
  } catch (error) {
    $('rodStatus').textContent = `杆件识别未完成：${error.message}`;
  } finally { button.disabled = false; }
}

function selectedRodCandidates() {
  return state.rodCandidates.filter((candidate) => state.selectedRods.has(candidate.id));
}

function renderRodSummary() {
  const summary = $('rodSummary');
  if (!state.rodCandidates.length) { summary.classList.add('hidden'); $('sendToFrameCAEBtn').disabled = true; return; }
  summary.classList.remove('hidden');
  const suggested = state.rodCandidates.filter((c) => c.status === 'suggested').length;
  const review = state.rodCandidates.filter((c) => c.status === 'review').length;
  summary.innerHTML = `<span>已选 ${state.selectedRods.size} 条杆件</span><span>自动建议 ${suggested} 条</span><span>待复核 ${review} 条</span>`;
  $('sendToFrameCAEBtn').disabled = !state.result || !state.selectedRods.size || state.result.unit !== 'mm';
}

async function sendToFrameCAE() {
  if (!state.result || state.result.unit !== 'mm')
    return notify('请先输入已知点间的实际毫米距离并重新重建；相对尺度不能应用到工程画布。');
  if (!state.rodCandidates.length || !state.selectedRods.size)
    return notify('请先识别杆件，并人工确认至少一根连接。');
  if (!window.confirm('请确认已逐项查看杆件候选及照片投影叠图。将把当前勾选的 ' + state.selectedRods.size + ' 根杆件送往 FrameCAE 预览，是否继续？'))
    return;
  if (typeof window.frameCAECalibratedImagesSubmit !== 'function')
    return notify('请从 FrameCAE 主界面的图像建模入口打开此工作区。');
  try {
    const accepted = await window.frameCAECalibratedImagesSubmit({
      reconstruction: state.result, rodCandidates: state.rodCandidates,
      selectedRodIds: [...state.selectedRods],
    });
    if (accepted) notify('已将确认的节点和杆件发送至 FrameCAE 画布预览。', true);
    else notify('本次没有生成草案；请查看 FrameCAE 主界面提示，必要时补充材料或截面。');
  } catch (error) { notify('发送草案失败：' + error.message); }
}

function renderCandidateList() {
  const holder = $('candidateList');
  holder.innerHTML = '';
  for (const candidate of state.rodCandidates) {
    const row = document.createElement('label');
    row.className = `candidate${state.highlightedRod === candidate.id ? ' highlight' : ''}`;
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = state.selectedRods.has(candidate.id);
    input.addEventListener('change', () => {
      if (input.checked) state.selectedRods.add(candidate.id);
      else state.selectedRods.delete(candidate.id);
      renderRodSummary(); renderRodOverlays(); drawViewer();
    });
    const text = document.createElement('div');
    text.className = 'candidate-main';
    const caution = candidate.intermediate_node ? ` · 中间经过 ${escapeHTML(candidate.intermediate_node)}` : '';
    text.innerHTML = `<span class="candidate-name">${escapeHTML(candidate.label_a)} — ${escapeHTML(candidate.label_b)}</span><span class="candidate-meta">长度 ${formatNumber(candidate.length, 2)} ${escapeHTML(state.result.unit)} · ${candidate.support_views} 张图支持${caution}</span>`;
    const score = document.createElement('span');
    score.className = `candidate-score ${candidate.status}`;
    const statusText = candidate.status === 'suggested' ? '自动建议' :
      candidate.status === 'review' ? '待复核' : '证据较少';
    score.innerHTML = `${Math.round(candidate.score * 100)}%<small>${statusText}</small>`;
    row.append(input, text, score);
    row.addEventListener('mouseenter', () => highlightRod(candidate.id));
    row.addEventListener('click', () => highlightRod(candidate.id));
    holder.append(row);
  }
  renderRodSummary();
  renderRodPreviews();
}

function highlightRod(id) {
  if (state.highlightedRod === id) return;
  state.highlightedRod = id;
  workspaceRoot.querySelectorAll('.candidate').forEach((row, index) =>
    row.classList.toggle('highlight', state.rodCandidates[index].id === id));
  renderRodPreviews(); renderRodOverlays(); drawViewer();
}

function makeProjectionSvg(image, projection) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${image.width} ${image.height}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  if (projection) {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    line.setAttribute('points', projection.map((point) => point.join(',')).join(' '));
    line.setAttribute('fill', 'none');
    line.setAttribute('stroke', '#ffbd5c');
    line.setAttribute('stroke-width', String(Math.max(5, image.width * .003)));
    line.setAttribute('stroke-linecap', 'round');
    svg.append(line);
  }
  return svg;
}

function renderRodPreviews() {
  const holder = $('rodPreviews');
  holder.innerHTML = '';
  const candidate = state.rodCandidates.find((item) => item.id === state.highlightedRod);
  if (!candidate) return;
  state.images.forEach((image, index) => {
    const preview = document.createElement('div');
    preview.className = 'rod-preview';
    const label = document.createElement('div');
    label.className = 'rod-preview-label';
    label.textContent = `视图 ${index + 1} · ${image.name} · 线段证据 ${Math.round(candidate.evidence[index].score * 100)}%`;
    const visual = document.createElement('div');
    visual.className = 'rod-preview-image';
    const img = document.createElement('img');
    img.src = image.url;
    img.alt = `视图 ${index + 1} 的候选杆投影`;
    visual.append(img, makeProjectionSvg(image, candidate.projections[index]));
    preview.append(label, visual);
    holder.append(preview);
  });
}

function renderRodOverlays() {
  workspaceRoot.querySelectorAll('.rod-layer').forEach((svg) => {
    const index = Number(svg.dataset.viewIndex);
    const image = state.images[index];
    svg.replaceChildren();
    if (!image) return;
    svg.setAttribute('viewBox', `0 0 ${image.width} ${image.height}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    for (const candidate of state.rodCandidates) {
      const highlighted = candidate.id === state.highlightedRod;
      if (!highlighted && !state.selectedRods.has(candidate.id)) continue;
      const projection = candidate.projections[index];
      if (!projection) continue;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      line.setAttribute('points', projection.map((point) => point.join(',')).join(' '));
      line.setAttribute('fill', 'none');
      line.setAttribute('stroke', highlighted ? '#ffbd5c' : '#69d4a1');
      line.setAttribute('stroke-width', String(Math.max(6, image.width * .0025)));
      line.setAttribute('stroke-opacity', highlighted ? '1' : '.75');
      line.setAttribute('stroke-linecap', 'round');
      svg.append(line);
    }
  });
}

function downloadPLY() {
  if (!state.result) return;
  const items = state.result.points;
  const header = ['ply', 'format ascii 1.0', `comment units ${state.result.unit}`,
    `element vertex ${items.length}`, 'property float x', 'property float y',
    'property float z', 'end_header'];
  downloadText('reconstructed_points.ply', [...header,
    ...items.map((p) => p.xyz.join(' '))].join('\n') + '\n');
}

function downloadCSV() {
  if (!state.result) return;
  const lines = [`id,label,x_${state.result.unit},y_${state.result.unit},z_${state.result.unit},rmse_px`,
    ...state.result.points.map((p) => [p.id, `"${p.label.replaceAll('"', '""')}"`,
      ...p.xyz, p.rmse_px].join(','))];
  downloadText('reconstructed_points.csv', '\ufeff' + lines.join('\n') + '\n', 'text/csv;charset=utf-8');
}

function checkedRods() {
  const selected = selectedRodCandidates();
  if (!state.result || !selected.length) {
    notify('请先完成杆件识别，并至少勾选一条连接。');
    return null;
  }
  return selected;
}

function downloadRodsCSV() {
  const rods = checkedRods();
  if (!rods) return;
  const lines = ['node_a,node_b,label_a,label_b,length,unit,image_score,support_views,classification',
    ...rods.map((rod) => [rod.a, rod.b, `"${rod.label_a.replaceAll('"', '""')}"`,
      `"${rod.label_b.replaceAll('"', '""')}"`, rod.length, state.result.unit,
      rod.score, rod.support_views, rod.status].join(','))];
  downloadText('reconstructed_rods.csv', '\ufeff' + lines.join('\n') + '\n', 'text/csv;charset=utf-8');
}

function rodDiameterValue() {
  const text = $('rodDiameter').value.trim();
  if (!text) return null;
  const value = Number(text);
  if (!Number.isFinite(value) || value <= 0) throw new Error('杆件直径必须大于 0。');
  return value;
}

function downloadRodsJSON() {
  const rods = checkedRods();
  if (!rods) return;
  try {
    const document = {
      format: 'manual-multiview-rod-model-v1',
      unit: state.result.unit,
      rod_diameter: rodDiameterValue(),
      nodes: state.result.points,
      rods: rods.map(({a, b, label_a, label_b, length, score, support_views,
                       status, evidence}) => ({a, b, label_a, label_b, length,
                                                score, support_views, status, evidence})),
      cameras: state.result.cameras,
      annotations: annotationData(),
      reconstruction_rmse_px: state.result.overall_rmse_px,
    };
    downloadText('reconstructed_rod_model.json', JSON.stringify(document, null, 2), 'application/json');
  } catch (error) { notify(error.message); }
}

function downloadRodsOBJ() {
  const rods = checkedRods();
  if (!rods) return;
  try {
    const nodes = Object.fromEntries(state.result.points.map((point) => [point.id, point.xyz]));
    const coordinates = state.result.points.map((point) => point.xyz);
    const min = [0, 1, 2].map((axis) => Math.min(...coordinates.map((p) => p[axis])));
    const max = [0, 1, 2].map((axis) => Math.max(...coordinates.map((p) => p[axis])));
    const visualDiameter = Math.max(...max.map((value, axis) => value - min[axis])) * .02;
    const specifiedDiameter = rodDiameterValue();
    const radius = (specifiedDiameter ?? visualDiameter) / 2;
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const normalize = (v) => { const n = Math.hypot(...v); return v.map((x) => x / n); };
    const lines = [`# Sparse rod model`, `# coordinate unit: ${state.result.unit}`,
      `# diameter: ${specifiedDiameter ?? visualDiameter} (${specifiedDiameter ? 'user supplied' : 'display only'})`];
    let vertexIndex = 1;
    const sides = 12;
    for (const rod of rods) {
      const a = nodes[rod.a], b = nodes[rod.b];
      if (!a || !b) continue;
      const axis = normalize(b.map((x, i) => x - a[i]));
      const reference = Math.abs(axis[2]) < .9 ? [0, 0, 1] : [0, 1, 0];
      const u = normalize(cross(axis, reference));
      const v = cross(axis, u);
      lines.push(`o rod_${rod.a}_${rod.b}`);
      for (const center of [a, b]) {
        for (let side = 0; side < sides; side++) {
          const angle = side * 2 * Math.PI / sides;
          const xyz = center.map((value, i) => value + radius *
            (Math.cos(angle) * u[i] + Math.sin(angle) * v[i]));
          lines.push(`v ${xyz.join(' ')}`);
        }
      }
      for (let side = 0; side < sides; side++) {
        const next = (side + 1) % sides;
        const i0 = vertexIndex + side, i1 = vertexIndex + next;
        const i2 = vertexIndex + sides + next, i3 = vertexIndex + sides + side;
        lines.push(`f ${i0} ${i1} ${i2}`, `f ${i0} ${i2} ${i3}`);
      }
      for (let side = 1; side < sides - 1; side++) {
        lines.push(`f ${vertexIndex} ${vertexIndex + side + 1} ${vertexIndex + side}`);
        lines.push(`f ${vertexIndex + sides} ${vertexIndex + sides + side} ${vertexIndex + sides + side + 1}`);
      }
      vertexIndex += 2 * sides;
    }
    downloadText('reconstructed_rod_model.obj', lines.join('\n') + '\n');
  } catch (error) { notify(error.message); }
}

function installViewerControls() {
  const canvas = $('pointViewer');
  let last = null;
  canvas.addEventListener('pointerdown', (event) => {
    last = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!last) return;
    state.yaw += (event.clientX - last[0]) * .008;
    state.pitch = Math.max(-1.5, Math.min(1.5, state.pitch + (event.clientY - last[1]) * .008));
    last = [event.clientX, event.clientY]; drawViewer();
  });
  canvas.addEventListener('pointerup', () => { last = null; });
  canvas.addEventListener('pointercancel', () => { last = null; });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    state.viewerZoom = Math.max(.3, Math.min(8, state.viewerZoom * (event.deltaY < 0 ? 1.12 : .89)));
    drawViewer();
  }, {passive: false});
  window.addEventListener('resize', drawViewer);
}

async function init() {
  $('imageInput').addEventListener('change', handleImages);
  $('newTrackBtn').addEventListener('click', addTrack);
  $('clearTrackBtn').addEventListener('click', () => removeCurrentTrack(true));
  $('deleteTrackBtn').addEventListener('click', () => removeCurrentTrack(false));
  $('exportMarksBtn').addEventListener('click', () => {
    if (!state.images.length) return notify('请先上传照片。');
    downloadText('manual_correspondences.json', JSON.stringify(annotationData(), null, 2), 'application/json');
  });
  $('importMarksInput').addEventListener('change', importAnnotations);
  $('reconstructBtn').addEventListener('click', runReconstruction);
  $('downloadPlyBtn').addEventListener('click', downloadPLY);
  $('downloadCsvBtn').addEventListener('click', downloadCSV);
  $('downloadResultBtn').addEventListener('click', () => {
    if (state.result) downloadText('multiview_reconstruction.json', JSON.stringify({
      annotations: annotationData(), reconstruction: state.result}, null, 2), 'application/json');
  });
  $('inferRodsBtn').addEventListener('click', runRodInference);
  $('downloadRodsCsvBtn').addEventListener('click', downloadRodsCSV);
  $('downloadRodsObjBtn').addEventListener('click', downloadRodsOBJ);
  $('downloadRodsJsonBtn').addEventListener('click', downloadRodsJSON);
  $('sendToFrameCAEBtn').addEventListener('click', sendToFrameCAE);
  window.addEventListener('keydown', (event) => {
    if (workspaceHost?.closest('#calibratedImageOverlay')?.hidden) return;
    const target = event.composedPath()[0];
    if (event.key.toLowerCase() === 'n' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(target?.tagName))
      addTrack();
  });
  installViewerControls();
  addTrack();
  try {
    const response = await fetch('/api/image-reconstruction/calibration');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '无法读取标定文件。');
    if (data.interface_version !== 4 || data.min_baseline_matches !== 7)
      throw new Error('当前页面连接的是旧版计算服务。请重启 FrameCAE 并使用新打开的地址。');
    state.calibration = data;
    $('calibrationStatus').textContent = `7 节点 · 杆件识别版已连接 · ${data.image_size_px.join(' × ')} · 标定 RMS ${Number(data.calibration_rms_px).toFixed(3)} px`;
  } catch (error) {
    $('calibrationStatus').textContent = '相机标定未加载';
    notify(error.message);
  }
}

init();
})();

