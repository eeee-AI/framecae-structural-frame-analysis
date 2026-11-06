(() => {
  const main = document.querySelector('main');
  const editor = document.querySelector('#editor');
  const viewer = document.querySelector('#viewer');
  if (!main || document.querySelector('#moduleHub')) return;

  const style = document.createElement('style');
  style.textContent = `
    #moduleHub{max-width:1120px;margin:34px auto;padding:0 16px}.hub-title{margin:0 0 8px;font-size:28px;color:#172f50}.hub-lead{margin:0 0 24px;color:#64748b;font-size:15px}.hub-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.hub-card{padding:22px;min-height:176px;text-align:left;border:1px solid #d6e1f0;border-radius:12px;background:#fff;color:#172033;box-shadow:0 3px 12px #142b4a12}.hub-card:hover{border-color:#1667c9;background:#f7fbff}.hub-card b{display:block;font-size:19px;margin-bottom:9px;color:#155ca8}.hub-card span{display:block;line-height:1.65;color:#64748b}.module-bar{display:flex;align-items:center;gap:10px;padding:0 0 10px;border-bottom:1px solid #d8e0ec;margin-bottom:10px}.module-bar strong{font-size:16px}.module-back{background:#eef3fa;color:#1d4f88;border:1px solid #c9d8eb}.module-placeholder{padding:22px;background:#f8fbff;border:1px dashed #b8cbe3;border-radius:8px;line-height:1.8;color:#40516a}#viewer{position:relative}#calculationProgress{position:absolute;z-index:20;right:14px;top:52px;display:flex;align-items:center;gap:8px;max-width:calc(100% - 28px);padding:8px 11px;border:1px solid #cbdced;border-radius:8px;background:#fffffff2;color:#34516f;box-shadow:0 2px 8px #183a5a1a;font-size:13px;line-height:1.3;pointer-events:none}.progress-dot{width:8px;height:8px;flex:0 0 8px;border-radius:999px;background:#7190ad}.is-working .progress-dot{background:#1672d3;animation:framecaePulse 1s ease-in-out infinite}.is-complete .progress-dot{background:#27a25a}.is-error .progress-dot{background:#dc4d4d}@keyframes framecaePulse{50%{opacity:.25;transform:scale(.65)}}@media(max-width:720px){.hub-grid{grid-template-columns:1fr}.hub-title{font-size:23px}#calculationProgress{top:46px;left:10px;right:10px;max-width:none}}
  `;
  document.head.append(style);

  const hub = document.createElement('section');
  hub.id = 'moduleHub';
  hub.innerHTML = `<h2 class="hub-title">FrameCAE 分析工作台</h2><p class="hub-lead">选择一个模块开始工作。页面只显示该模块所需的输入、计算和结果。</p><div class="hub-grid">
    <button class="hub-card" data-module="global"><b>01　整体空间刚架求解</b><span>在三维网格中搭建杆系，或编辑材料、截面、节点、支座与荷载；求解位移、支座反力和杆件内力。</span></button>
    <button class="hub-card" data-module="strength"><b>02　危险截面与强度校核</b><span>选择荷载工况，扫描危险截面，比较 Rankine、最大主应变、Tresca、von Mises，并显示利用率图。</span></button>
    <button class="hub-card" data-module="local"><b>03　节点局部实体应力集中</b><span>读取整体截面运动与节点外载，调用 Abaqus 分析一体节点件、环焊缝及邻接管壁应力。</span></button>
    <button class="hub-card" data-module="stability"><b>04　构件稳定校核</b><span>基于整体计算得到的受压轴力，计算 Euler 临界力、长细比、控制屈曲轴与稳定利用率。</span></button>
    <button class="hub-card" data-module="forces"><b>05　杆件内力图</b><span>在三维杆系上直接显示弯矩 My/Mz、扭矩 T 与拉压轴力 N 的正负内力图。</span></button>
    <button class="hub-card" data-module="fullStress"><b>06　满应力计算</b><span>固定材料体积，逐轮重算三维刚架的内力、强度和稳定利用率。</span></button>
  </div>`;
  main.insertAdjacentElement('beforebegin', hub);

  const bar = document.createElement('div');
  bar.className = 'module-bar';
  bar.innerHTML = '<button class="module-back">← 返回模块首页</button><strong id="moduleTitle"></strong><span class="help" id="moduleDescription"></span>';
  editor.insertAdjacentElement('afterbegin', bar);
  const top = editor.querySelector('.top');
  const calculationProgress = document.createElement('div');
  calculationProgress.id = 'calculationProgress';
  calculationProgress.setAttribute('role', 'status');
  calculationProgress.setAttribute('aria-live', 'polite');
  calculationProgress.innerHTML = '<span class="progress-dot"></span><span></span>';
  viewer.append(calculationProgress);
  const updateCalculationProgress = () => {
    const message = document.querySelector('#status')?.textContent?.trim() || '等待计算。';
    const working = /正在|求解中|计算中|扫描中|组装中/.test(message);
    const failed = /修正|失败|错误|未完成/.test(message);
    calculationProgress.className = working ? 'is-working' : failed ? 'is-error' : 'is-complete';
    calculationProgress.querySelector('span:last-child').textContent = working ? `计算中：${message}` : message;
  };
  updateCalculationProgress();
  new MutationObserver(updateCalculationProgress).observe(document.querySelector('#status'), {childList: true, characterData: true, subtree: true});
  const defaultCase = document.querySelector('#default');
  const verification = document.querySelector('#verification');
  const tJointDemo = document.querySelector('#loadT');
  const returnGlobal = document.querySelector('#returnGlobal');
  const tables = document.querySelector('#tables');
  const visualBuilder = document.querySelector('#visualBuilderSettings');
  const aiAssistant = document.querySelector('#aiModelingAssistant');
  const selfWeight = document.querySelector('#selfWeightSettings');
  const assembly = document.querySelector('#assemblySettings');
  const strength = document.querySelector('#strengthCheckSettings');
  const stability = document.querySelector('#stabilityCheckSettings');
  const fullStress = document.querySelector('#fullStressSettings');
  const internalForce = document.querySelector('#internalForceSettings');
  const genericLocal = document.querySelector('#genericLocalSettings');
  const standardLocal = document.querySelector('#localSettings');
  const trailingHelp = Array.from(editor.children).filter(child => child.tagName === 'P');
  const allSections = [visualBuilder, tables, selfWeight, assembly, strength, stability, fullStress, internalForce, genericLocal, standardLocal, ...trailingHelp].filter(Boolean);
  const setDisplay = (element, visible, display = '') => { if (element) element.style.display = visible ? display : 'none'; };
  const metadata = {
    global: ['整体空间刚架求解', '可在三维网格中创建、拖动和连接杆件；材料、截面、荷载、支座与其它参数仍可在表格中精确编辑。'],
    strength: ['危险截面与强度校核', '先定义工况，再比较四大强度理论的危险截面与利用率。'],
    local: ['节点局部实体应力集中', '读取 01 已确认结构，建立一体节点件与环形对接焊局部实体模型，并通过 Abaqus 求解。'],
    stability: ['构件稳定校核', '基于整体刚架的受压轴力，按 Euler 理论比较临界力、长细比与稳定利用率。'],
    forces: ['杆件内力图', '在右侧三维杆系上按局部坐标与正负号显示弯矩、扭矩和拉压轴力。'],
    fullStress: ['满应力计算', '固定材料体积，逐轮重算三维刚架响应并调整完整截面。'],
  };
  const show = module => {
    window.frameCAEActiveModule = module;
    window.dispatchEvent(new CustomEvent('framecae-module-change', {detail: {module}}));
    if (module === 'global') displayMode = 'global';
    hub.style.display = 'none';
    main.style.display = 'grid';
    main.classList.toggle('module-strength', module === 'strength');
    setDisplay(editor, true, 'block');
    setDisplay(top, module === 'global', 'flex');
    // 演示模型只允许在整体建模入口加载，后续模块始终分析已确认结构。
    setDisplay(defaultCase, module === 'global');
    setDisplay(verification, module === 'global');
    setDisplay(tJointDemo, false);
    setDisplay(returnGlobal, false);
    allSections.forEach(section => setDisplay(section, false));
    setDisplay(document.querySelector('#framecaeModelingWorkbench'), false);
    setDisplay(aiAssistant, false);
    setDisplay(viewer, true, 'grid');
    window.frameCAEForceDiagramActive?.(module === 'forces');
    if (module === 'global') {
      const modelingSection = document.querySelector('#framecaeModelingWorkbench') || visualBuilder;
      modelingSection.insertAdjacentElement('afterend', tables);
      setDisplay(modelingSection, true, 'block');
      if (modelingSection === visualBuilder) setDisplay(aiAssistant, true, 'block');
      else window.frameCAEModelingWorkbenchRefresh?.();
      setDisplay(tables, true); setDisplay(selfWeight, true, 'block'); setDisplay(assembly, true, 'block'); trailingHelp.forEach(item => setDisplay(item, true)); window.frameCAERefreshVisualBuilder?.();
    } else if (module === 'strength') {
      setDisplay(strength, true, 'block');
    } else if (module === 'local') {
      // 03 只分析 01 中确认的实际连接关系；旧的固定 T 形演示不再作为入口。
      setDisplay(genericLocal, true, 'block'); setDisplay(standardLocal, false);
    } else if (module === 'forces') {
      setDisplay(internalForce, true, 'block'); window.frameCAERefreshInternalForce?.();
    } else if (module === 'fullStress') {
      setDisplay(fullStress, true, 'block');
    } else {
      setDisplay(stability, true, 'block'); window.frameCAERefreshStability?.();
    }
    document.querySelector('#moduleTitle').textContent = metadata[module][0];
    document.querySelector('#moduleDescription').textContent = metadata[module][1];
    window.scrollTo({top: 0, behavior: 'smooth'});
  };
  const home = () => { main.style.display = 'none'; hub.style.display = 'block'; window.scrollTo({top: 0, behavior: 'smooth'}); };
  hub.querySelectorAll('[data-module]').forEach(button => button.onclick = () => show(button.dataset.module));
  bar.querySelector('.module-back').onclick = home;
  window.frameCAEOpenModule = show;
  window.frameCAEOpenHome = home;
  home();
})();
