/* Independent Abaqus/Standard check for the current 03 standalone model. */
(() => {
  // Kept for future independent checks; disabled by this round's server flag.
  if(window.FRAMECAE_ABAQUS_VERIFICATION_ENABLED===false)return;
  const $ = s => document.querySelector(s);
  const host = $('#abaqusHubSettings');
  if (!host || !window.FrameCAESolidPanel) return;
  const section = document.createElement('section');
  section.id = 'abaqusVerifyPanel';
  section.style.cssText = 'margin-top:18px;padding:16px;border:1px solid #8ba6ce;border-radius:10px;background:#f4f7fc';
  section.innerHTML = `<h4>Abaqus 独立验证</h4>
    <p class="help">对当前 01→03 局部模型使用同一份曲边 Tet10 网格、材料、所选边界条件和载荷，由 Abaqus/Standard 独立求解。这是同一局部问题的求解器核验；生成的 ODB 可由 Abaqus/Viewer 打开。</p>
    <div class="actions"><button id="avGenerate" type="button">① 生成 INP</button>
      <button id="avSolve" type="button" disabled>② 用 Abaqus 计算</button>
      <button id="avViewer" type="button" disabled>③ 打开 Abaqus Viewer</button></div>
    <div class="actions"><input id="avJobId" type="text" maxlength="32" placeholder="上次验证作业编号" style="max-width:290px">
      <button id="avRestore" type="button" class="secondary">读取作业</button></div>
    <p id="avStatus" class="help" role="status">正在检查 Abaqus 启动器…</p>
    <div id="avFiles" class="help"></div>`;
  host.append(section);
  const active = () => window.frameCAEUseStandaloneLocal?.() && document.body.dataset.module === 'local';
  const base = '/api/abaqus-verify/jobs/';
  let job = '', fingerprint = '', pendingSignature = '', processing = false, available = false, autoOpened = false;
  $('#avJobId').value = localStorage.getItem('framecaeAbaqusVerifyLastJob') || '';
  const signature = () => window.FrameCAESolidPanel.signature();
  async function api(url, body) {
    const response = await fetch(url, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Abaqus 验证请求失败。');
    return result;
  }
  function message(value, error = false) {
    $('#avStatus').textContent = value;
    $('#avStatus').style.color = error ? '#a92323' : '';
  }
  function refresh() {
    section.hidden = !active();
    const same = !!job && pendingSignature === signature();
    $('#avGenerate').disabled = processing || !window.frameCAEHasConfirmedModel?.();
    $('#avRestore').disabled = processing;
    $('#avSolve').disabled = processing || !available || !same || !$('#avSolve').dataset.ready;
    $('#avViewer').disabled = !available || !same || !$('#avViewer').dataset.ready;
    if (job && !same) message('当前 01/03 输入已改变；请重新生成 INP。', true);
  }
  function showFiles(files) {
    const names = ['model.inp', 'verify.sta', 'verify.msg', 'abaqus.log', 'verify.odb'];
    $('#avFiles').replaceChildren();
    for (const name of names.filter(n => files.includes(n))) {
      const link = document.createElement('a');
      link.href = base + job + '/files/' + name;
      link.download = name;
      link.textContent = name;
      $('#avFiles').append(link, document.createTextNode(' · '));
    }
  }
  async function poll(phase) {
    for (;;) {
      const state = await api(base + job);
      message(state.message || state.state);
      showFiles(state.files || []);
      if (state.state === 'failed') throw Error(state.message || 'Abaqus 作业失败。');
      if (phase === 'generate' && state.state === 'inp_ready') {
        $('#avSolve').dataset.ready = '1';
        processing = false; refresh(); return;
      }
      if (phase === 'solve' && state.state === 'completed') {
        $('#avViewer').dataset.ready = '1';
        processing = false; refresh();
        if (pendingSignature === signature() && !autoOpened) {
          autoOpened = true;
          try { await openViewer(); }
          catch (error) { message('计算完成，但自动打开 Viewer 失败：' + error.message, true); }
        }
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
  }
  async function openViewer() {
    const response = await api(base + job + '/viewer', {});
    message('已启动 Abaqus Viewer，正在打开 ' + response.odb);
  }
  $('#avGenerate').onclick = async () => {
    if (!active() || processing) return;
    if (!window.frameCAEHasConfirmedModel?.()) return message('请先确认 01 模型并完成整体求解。', true);
    processing = true; job = ''; autoOpened = false;
    delete $('#avSolve').dataset.ready;
    delete $('#avViewer').dataset.ready;
    pendingSignature = signature(); refresh();
    try {
      const response = await api('/api/abaqus-verify/jobs', {model: payload(), settings: genericLocalSettings()});
      job = response.jobId; fingerprint = response.fingerprint;
      localStorage.setItem('framecaeAbaqusVerifyLastJob', job);
      $('#avJobId').value = job;
      message(response.message + ' 作业编号：' + job);
      await poll('generate');
    } catch (error) { processing = false; message(error.message, true); refresh(); }
  };
  $('#avSolve').onclick = async () => {
    if (!job || processing || pendingSignature !== signature()) return;
    processing = true; delete $('#avSolve').dataset.ready; refresh();
    try {
      await api(base + job + '/solve', {});
      await poll('solve');
    } catch (error) { processing = false; message(error.message, true); refresh(); }
  };
  $('#avViewer').onclick = async () => {
    try { await openViewer(); }
    catch (error) { message(error.message, true); }
  };
  $('#avRestore').onclick = async () => {
    if (processing) return;
    processing = true; refresh();
    try {
      const id = $('#avJobId').value.trim();
      if (!/^[0-9a-f]{32}$/.test(id)) throw Error('请输入有效的作业编号。');
      const current = await api('/api/solid-local/prepare', {model: payload(), settings: genericLocalSettings()});
      const state = await api(base + id);
      if (state.fingerprint !== current.fingerprint) throw Error('该作业与当前 01/03 模型和参数不一致。');
      job = id; fingerprint = state.fingerprint; pendingSignature = signature();
      localStorage.setItem('framecaeAbaqusVerifyLastJob', job);
      showFiles(state.files || []);
      if (state.state === 'generating') return await poll('generate');
      if (state.state === 'solving') return await poll('solve');
      if (state.state === 'inp_ready') $('#avSolve').dataset.ready = '1';
      if (state.state === 'completed') $('#avViewer').dataset.ready = '1';
      message(state.message || state.state, state.state === 'failed');
    } catch (error) { message(error.message, true); }
    finally { processing = false; refresh(); }
  };
  api('/api/abaqus-verify/environment').then(result => {
    available = result.available;
    message(result.message + (available ? '' : ' 请检查安装位置。'));
    refresh();
  }).catch(error => message(error.message, true));
  window.addEventListener('framecae-module-change', refresh);
  window.addEventListener('framecae:model-state', refresh);
  $('#genericSolverMethod').addEventListener('change', refresh);
  $('#genericConnectionType').addEventListener('change', refresh);
  setInterval(refresh, 1000);
  refresh();
})();
