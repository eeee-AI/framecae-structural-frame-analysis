(() => {
  const anchor = document.querySelector('#aiModelingAssistant') || document.querySelector('#visualBuilderSettings');
  if (!anchor || document.querySelector('#calibratedImageModeling')) return;

  const panel = document.createElement('details');
  panel.id = 'calibratedImageModeling';
  panel.open = true;
  panel.style.cssText = 'margin-top:12px;padding:12px 14px;border:1px solid #aed8c0;border-radius:10px;background:#f6fffa;color:#254a37';
  panel.innerHTML = '<summary style="font-weight:700;cursor:pointer">图像建模 · 标定多视图节点与杆件</summary>' +
    '<p style="font-size:13px;line-height:1.6">使用同一台已标定相机的 2–4 张原比例照片，逐图标注至少 7 个同名点；输入已知毫米距离后重建三维节点，并人工复核杆件。不会使用旧版近似内参或手填连接表。</p>' +
    '<div style="display:flex;flex-wrap:wrap;gap:8px"><button id="openCalibratedImages">打开图像建模工作区</button>' +
    '<button id="applyCalibratedImages" class="secondary" disabled>应用已预览草案</button>' +
    '<button id="clearCalibratedPreview" class="secondary" disabled>清除预览</button></div>' +
    '<p id="calibratedImageStatus" style="min-height:24px;font-size:13px;color:#28629c">等待照片标注。未确定实际尺度时只能查看相对模型。</p>';
  anchor.insertAdjacentElement('afterend', panel);

  const overlay = document.createElement('div');
  overlay.id = 'calibratedImageOverlay';
  overlay.hidden = true;
  overlay.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#fff;display:none;flex-direction:column';
  overlay.innerHTML = '<div style="padding:7px 12px;background:#193853;color:#fff;display:flex;justify-content:space-between;align-items:center"><span>FrameCAE · 标定多视图图像建模</span><button id="closeCalibratedImages" type="button">返回 FrameCAE</button></div><div id="calibratedImageWorkspace" style="flex:1;min-height:0;overflow:auto"></div>';
  document.body.append(overlay);

  const workspace = overlay.querySelector('#calibratedImageWorkspace');
  const status = panel.querySelector('#calibratedImageStatus');
  const applyButton = panel.querySelector('#applyCalibratedImages');
  const clearButton = panel.querySelector('#clearCalibratedPreview');
  const builder = document.querySelector('#visualBuilderSettings');
  const previewActions = document.createElement('div');
  previewActions.id = 'calibratedImagePreviewActions';
  previewActions.style.cssText = 'display:none;margin:10px 0 14px;padding:12px;border:1px solid #b7a2df;border-radius:9px;background:#f7f2ff;color:#482b78;font-size:13px;line-height:1.6';
  previewActions.innerHTML = '<strong>图像建模草案预览中</strong><div id="calibratedPreviewSummary">紫色虚线是待确认的节点和杆件，尚未写入模型。</div>' +
    '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:9px"><button id="applyCalibratedFromBuilder" type="button">应用图像草案</button>' +
    '<button id="clearCalibratedFromBuilder" class="secondary" type="button">清除预览</button>' +
    '<button id="returnCalibratedWorkspace" class="secondary" type="button">返回图像工作区</button></div>';
  builder?.querySelector('.builder-layout')?.before(previewActions);
  const previewApplyButton = previewActions.querySelector('#applyCalibratedFromBuilder');
  let draft = null;
  let baseSnapshot = null;
  let workspaceLoad = null;
  const setStatus = message => { status.textContent = message; };
  const closeOverlay = () => { overlay.hidden = true; overlay.style.display = 'none'; };
  const showPreviewActions = visible => { previewActions.style.display = visible ? 'block' : 'none'; };
  previewApplyButton.onclick = () => applyButton.click();
  previewActions.querySelector('#clearCalibratedFromBuilder').onclick = () => clearButton.click();
  previewActions.querySelector('#returnCalibratedWorkspace').onclick = () => panel.querySelector('#openCalibratedImages').click();

  async function loadWorkspace() {
    const healthResponse = await fetch('/api/health', {cache: 'no-store'});
    if (!healthResponse.ok || !(healthResponse.headers.get('content-type') || '').includes('application/json'))
      throw Error('FrameCAE 本地服务不可用，请重新启动并使用启动窗口显示的新地址。');
    const health = await healthResponse.json();
    if (!health.features?.includes('calibratedImageReconstructionV3'))
      throw Error('当前运行的是旧版 FrameCAE，请关闭旧服务并重新启动本项目。');
    const pageResponse = await fetch('/image-reconstruction/', {cache: 'no-store'});
    if (!pageResponse.ok || !(pageResponse.headers.get('content-type') || '').includes('text/html'))
      throw Error('图像工作区资源未加载，请检查 FrameCAE 安装文件。');
    const page = new DOMParser().parseFromString(await pageResponse.text(), 'text/html');
    const shell = page.querySelector('.app-shell');
    if (!shell) throw Error('图像工作区页面结构不完整。');
    workspace.textContent = '';
    const root = workspace.shadowRoot || workspace.attachShadow({mode: 'open'});
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = '/image-reconstruction/style.css';
    root.replaceChildren(stylesheet, document.importNode(shell, true));
    const script = document.createElement('script');
    script.src = '/image-reconstruction/app.js';
    await new Promise((resolve, reject) => {
      script.onload = resolve;
      script.onerror = () => reject(Error('图像工作区脚本未加载，请检查 FrameCAE 安装文件。'));
      document.body.append(script);
    });
  }

  panel.querySelector('#openCalibratedImages').onclick = async () => {
    overlay.hidden = false;
    overlay.style.display = 'flex';
    if (!workspaceLoad) {
      workspace.textContent = '正在检查本地服务并加载图像工作区…';
      workspaceLoad = loadWorkspace().catch(error => {
        const message = '无法打开图像工作区：' + error.message;
        if (workspace.shadowRoot) workspace.shadowRoot.replaceChildren(document.createTextNode(message));
        else workspace.textContent = message;
        setStatus('图像工作区加载失败：' + error.message);
        workspaceLoad = null;
      });
    }
    await workspaceLoad;
  };
  overlay.querySelector('#closeCalibratedImages').onclick = closeOverlay;
  window.frameCAECalibratedImagesSubmit = async data => {
    const assistant = window.frameCAEModelAssistant;
    if (!assistant) { setStatus('画布尚未初始化，请刷新页面后重试。'); return false; }
    const baseModel = assistant.currentModel();
    const material = baseModel.materials?.[0], section = baseModel.sections?.[0];
    if (!material || !section) { setStatus('当前模型没有材料或截面，请先在主界面填写。'); return false; }
    const confirmation = '照片不能推断材料、截面、支座或荷载。\n\n本次草案是否使用当前首项材料和截面？' +
      '\n材料 E=' + material.e + ' GPa，ν=' + material.nu + '，密度=' + material.density + ' kg/m³' +
      '\n截面 A=' + section.a + ' m²，Iy=' + section.iy + ' m⁴，Iz=' + section.iz + ' m⁴。' +
      '\n\n如需其他参数，请取消，先在主界面修改材料和截面，再重新发送草案。';
    if (!window.confirm(confirmation)) { setStatus('已取消本次参数确认；可修改材料和截面后重新发送。'); return false; }
    setStatus('正在校验标定重建结果、毫米到米的换算及所选杆件…');
    try {
      const response = await fetch('/api/image-reconstruction/draft', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
          reconstruction: data.reconstruction,
          rodCandidates: data.rodCandidates,
          selectedRodIds: data.selectedRodIds,
          baseModel, confirmedMaterialSection: true,
        })});
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) throw Error('当前后端缺少新版图像建模接口，请重新启动 FrameCAE。');
      const proposal = await response.json();
      if (!response.ok || proposal.error) throw Error(proposal.error || '图像建模草案校验失败。');
      assistant.preview(proposal);
      draft = proposal;
      baseSnapshot = JSON.stringify(baseModel);
      applyButton.disabled = false;
      clearButton.disabled = false;
      previewApplyButton.disabled = false;
      previewActions.querySelector('#calibratedPreviewSummary').textContent =
        proposal.summary.nodeCount + ' 个节点、' + proposal.summary.elementCount + ' 根杆件。紫色虚线尚未写入模型；核对后再应用。';
      showPreviewActions(true);
      closeOverlay();
      document.querySelector('#modelTab0')?.click();
      if (builder) builder.open = true;
      window.requestAnimationFrame(() => {
        window.frameCAERefreshVisualBuilder?.();
        previewActions.scrollIntoView({behavior: 'smooth', block: 'center'});
      });
      setStatus('已预览 ' + proposal.summary.nodeCount + ' 个标定重建节点、' + proposal.summary.elementCount +
        ' 根人工确认杆件；坐标已由 mm 转为 m。紫色虚线尚未写入模型。请核对方向和连接，再决定是否应用。');
      return true;
    } catch (error) { setStatus('图像草案失败：' + error.message); throw error; }
  };
  applyButton.onclick = () => {
    if (!draft) return;
    const assistant = window.frameCAEModelAssistant;
    if (JSON.stringify(assistant.currentModel()) !== baseSnapshot) {
      setStatus('当前模型已变化，请返回图像工作区重新发送草案。');
      applyButton.disabled = true;
      previewApplyButton.disabled = true;
      previewActions.querySelector('#calibratedPreviewSummary').textContent = '当前模型已变化，此草案不能直接应用。请清除预览后重新发送。';
      return;
    }
    if (!window.confirm('应用会替换当前节点、杆件、支座和荷载，但保留刚确认的材料和截面。照片没有推断支座或荷载，应用后须人工补充。确定继续吗？')) return;
    try {
      assistant.preview(draft);
      assistant.apply(draft);
      draft = null; baseSnapshot = null; applyButton.disabled = true; clearButton.disabled = true;
      previewApplyButton.disabled = true; showPreviewActions(false);
      setStatus('标定多视图草案已应用到画布。请补充并核对支座、荷载及工程坐标方向，再求解。');
    } catch (error) { setStatus('应用失败：' + error.message); }
  };
  clearButton.onclick = () => {
    window.frameCAEModelAssistant?.clearPreview();
    draft = null; baseSnapshot = null; applyButton.disabled = true; clearButton.disabled = true;
    previewApplyButton.disabled = true; showPreviewActions(false);
    setStatus('已清除图像草案预览，当前模型没有改变。');
  };
})();
