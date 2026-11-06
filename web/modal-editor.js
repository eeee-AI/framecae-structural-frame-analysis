/* 左侧编辑区：概览行打开居中编辑窗。保留原 DOM，避免破坏表格与建模控件的事件。 */
(() => {
  const editor = document.querySelector('#editor');
  if (!editor || document.querySelector('#framecaeEditorBackdrop')) return;

  const style = document.createElement('style');
  style.textContent = `
    #editor > details.framecae-modal-launcher,
    #editor > #tables > details.framecae-modal-launcher {
      border-top:1px solid #d8e0ec; padding:0; margin:0; background:transparent;
    }
    #editor > details.framecae-modal-launcher > summary,
    #editor > #tables > details.framecae-modal-launcher > summary {
      min-height:45px; padding:11px 8px 10px 2px; display:flex; align-items:center;
      gap:10px; color:#172033; font-weight:700; cursor:pointer; list-style:none;
    }
    #editor > details.framecae-modal-launcher > summary:hover,
    #editor > #tables > details.framecae-modal-launcher > summary:hover { color:#1667c9; background:#f6faff; }
    #editor > details.framecae-modal-launcher > summary::after,
    #editor > #tables > details.framecae-modal-launcher > summary::after { content:'编辑 ›'; margin-left:auto; color:#64748b; font-size:12px; transform:none; }
    #editor > details.framecae-modal-launcher > summary > span,
    #editor > #tables > details.framecae-modal-launcher > summary > span { margin-left:auto; color:#172033; }
    #editor > details.framecae-modal-launcher > summary > span + span,
    #editor > #tables > details.framecae-modal-launcher > summary > span + span { margin-left:0; }
    #framecaeEditorBackdrop { position:fixed; inset:0; z-index:90; display:none; background:rgba(15,30,51,.38); backdrop-filter:blur(2px); }
    #framecaeEditorBackdrop.is-visible { display:block; }
    details.framecae-modal-open {
      position:fixed !important; z-index:91; top:72px; bottom:24px; left:50%; width:min(1060px,calc(100vw - 40px));
      transform:translateX(-50%); overflow:auto; padding:0 20px 20px !important; border:1px solid #bed0e6 !important;
      border-radius:12px; background:#fff !important; box-shadow:0 20px 60px rgba(15,30,51,.28);
    }
    details.framecae-modal-open#visualBuilderSettings { width:min(1320px,calc(100vw - 40px)); }
    details.framecae-modal-open#aiModelingAssistant { width:min(820px,calc(100vw - 40px)); }
    details.framecae-modal-open#framecaeModelingWorkbench { width:min(1320px,calc(100vw - 40px)); }
    #framecaeModelingWorkbench .framecae-workbench-tabs { position:sticky; top:58px; z-index:2; display:flex; gap:8px; padding:10px 0; background:#fff; border-bottom:1px solid #d8e0ec; }
    #framecaeModelingWorkbench .framecae-workbench-tabs button { margin:0; }
    #framecaeModelingWorkbench .framecae-workbench-tabs button[aria-selected="true"] { background:#1767c8; color:#fff; border-color:#1767c8; }
    #framecaeModelingWorkbench .framecae-workbench-body > details { border:0 !important; padding:12px 0 0 !important; margin:0 !important; box-shadow:none !important; width:100%; }
    #framecaeModelingWorkbench .framecae-workbench-body > details > summary { display:none !important; }
    #framecaeModelingWorkbench #aiModelingAssistant .ai-modeling-body { padding:0; }
    details.framecae-modal-open > summary {
      position:sticky; top:0; z-index:2; min-height:58px; padding:17px 2px 14px !important; background:#fff;
      border-bottom:1px solid #d8e0ec; font-size:17px; color:#102e54;
    }
    details.framecae-modal-open > summary::after { content:'× 关闭' !important; color:#52677f !important; font-size:13px !important; }
    details.framecae-modal-open .table-wrap { max-height:min(56vh,520px); }
    @media (max-width:720px) { details.framecae-modal-open { top:10px; bottom:10px; width:calc(100vw - 20px); padding:0 12px 14px !important; } }
  `;
  document.head.append(style);

  const builder = document.querySelector('#visualBuilderSettings');
  const aiAssistant = document.querySelector('#aiModelingAssistant');
  if (builder && aiAssistant && !document.querySelector('#framecaeModelingWorkbench')) {
    const workbench = document.createElement('details');
    workbench.id = 'framecaeModelingWorkbench';
    workbench.dataset.activeTab = 'visual';
    workbench.innerHTML = '<summary>建模工作台 <span>可视化三维建模 / AI 建模助手</span></summary><div class="framecae-workbench-tabs" role="tablist" aria-label="建模方式"><button type="button" class="secondary" data-workbench-tab="visual" role="tab" aria-selected="true">可视化三维建模</button><button type="button" class="secondary" data-workbench-tab="ai" role="tab" aria-selected="false">AI 建模助手</button></div><div class="framecae-workbench-body"></div>';
    builder.insertAdjacentElement('beforebegin', workbench);
    const body = workbench.querySelector('.framecae-workbench-body');
    body.append(builder, aiAssistant);
    builder.open = true;
    aiAssistant.open = true;
    const showTab = tab => {
      workbench.dataset.activeTab = tab;
      builder.style.display = tab === 'visual' ? 'block' : 'none';
      aiAssistant.style.display = tab === 'ai' ? 'block' : 'none';
      workbench.querySelectorAll('[data-workbench-tab]').forEach(button => {
        const selected = button.dataset.workbenchTab === tab;
        button.setAttribute('aria-selected', String(selected));
        button.tabIndex = selected ? 0 : -1;
      });
      if (tab === 'visual') window.requestAnimationFrame(() => window.frameCAERefreshVisualBuilder?.());
    };
    workbench.querySelectorAll('[data-workbench-tab]').forEach(button => {
      button.addEventListener('click', () => showTab(button.dataset.workbenchTab));
    });
    workbench.addEventListener('click', event => {
      if (event.target.closest('#aiPreviewDraft, #aiApplyDraft')) showTab('visual');
    });
    window.frameCAEModelingWorkbenchRefresh = () => showTab(workbench.dataset.activeTab || 'visual');
    showTab('visual');
  }

  const backdrop = document.createElement('div');
  backdrop.id = 'framecaeEditorBackdrop';
  backdrop.setAttribute('aria-hidden', 'true');
  document.body.append(backdrop);
  let active = null;

  const close = () => {
    if (!active) return;
    active.classList.remove('framecae-modal-open');
    active.open = false;
    active = null;
    backdrop.classList.remove('is-visible');
    backdrop.setAttribute('aria-hidden', 'true');
  };
  const open = detail => {
    if (active === detail) return;
    close();
    active = detail;
    detail.open = true;
    detail.classList.add('framecae-modal-open');
    backdrop.classList.add('is-visible');
    backdrop.setAttribute('aria-hidden', 'false');
    if (detail.id === 'framecaeModelingWorkbench') window.requestAnimationFrame(() => window.frameCAEModelingWorkbenchRefresh?.());
    window.setTimeout(() => detail.querySelector('input, select, textarea, button')?.focus({preventScroll:true}), 0);
  };

  const shouldUseModal = () => !['strength', 'local', 'stability'].includes(window.frameCAEActiveModule);
  const visibleDetails = () => [...editor.querySelectorAll('details')].filter(detail => !detail.closest('#framecaeModelingWorkbench') || detail.id === 'framecaeModelingWorkbench');
  const prepare = detail => {
    if (!shouldUseModal()) {
      detail.classList.remove('framecae-modal-launcher', 'framecae-modal-open');
      detail.open = true;
      return;
    }
    if (detail.dataset.modalLauncherReady === 'true') {
      detail.classList.add('framecae-modal-launcher');
      return;
    }
    const summary = detail.querySelector(':scope > summary');
    if (!summary) return;
    detail.dataset.modalLauncherReady = 'true';
    detail.classList.add('framecae-modal-launcher');
    detail.open = false;
    summary.setAttribute('role', 'button');
    summary.setAttribute('tabindex', '0');
    summary.addEventListener('click', event => {
      if (!shouldUseModal()) return;
      event.preventDefault(); active === detail ? close() : open(detail);
    });
    summary.addEventListener('keydown', event => {
      if (!shouldUseModal()) return;
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); active === detail ? close() : open(detail); }
    });
  };
  const scan = () => visibleDetails().forEach(prepare);
  const refreshMode = () => {
    close();
    scan();
  };

  backdrop.addEventListener('click', close);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  window.addEventListener('framecae-module-change', refreshMode);
  // 新增／删除表格行会重绘 #tables；先关闭当前窗口，避免旧 DOM 残留在前景。
  document.addEventListener('click', event => {
    if (event.target.closest('#tables [data-add], #tables .remove')) close();
  }, true);
  new MutationObserver(() => {
    if (active && !active.isConnected) { active = null; backdrop.classList.remove('is-visible'); }
    scan();
  }).observe(editor, {childList:true, subtree:true});
  scan();
})();
