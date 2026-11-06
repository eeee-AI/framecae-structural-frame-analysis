/* Workflow shell. Existing controls and calculation handlers remain the source of truth. */
(() => {
  const $ = selector => document.querySelector(selector);
  const hub=$('#moduleHub'),main=$('main'),editor=$('#editor'),viewer=$('#viewer');
  if(!hub || $('#workspaceSidebar'))return;
  const css=document.createElement('link');css.rel='stylesheet';css.href='/workspace.css';document.head.append(css);
  document.body.classList.add('workspace-app');
  const paths={
    home:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    global:'<path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9M12 3v10"/>',
    forces:'<path d="M4 4v16h16M6 16l4-7 5 4 5-9M8 20v-5M13 20v-7M18 20V9"/>',
    strength:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
    stability:'<path d="M4 20h16M4 4h16M8 4v16M16 4c-6 5-6 11 0 16M2 8l2-4 2 4M18 16l2 4 2-4"/>',
    fullStress:'<path d="M3 20h18M6 17V9h4v8M14 17V5h4v12M4 6l5-3 5 2 6-3"/>',
    local:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M6 10h8M10 6v8"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',check:'<path d="m5 12 4 4L19 6"/>'};
  const icon=name=>`<svg class="ws-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
  const modules={
    global:{code:'01',title:'建模与整体计算',brief:'定义结构、材料、支座和荷载，确认后统一计算。'},
    forces:{code:'05',title:'位移与内力',brief:'查看变形、轴力、弯矩和扭矩，定位受力较大的杆件。'},
    strength:{code:'02',title:'截面强度校核',brief:'比较危险截面与材料强度，查看各杆件利用率。'},
    stability:{code:'04',title:'构件稳定校核',brief:'检查受压杆件的临界力、长细比与稳定利用率。'},
    local:{code:'03',title:'节点局部分析',brief:'选择圆管连接节点，查看局部应力与网格收敛。'},
    fullStress:{code:'06',title:'满应力计算',brief:'固定材料体积，迭代调整刚架截面并重算强度与稳定。'}};
  const header=$('body > header');
  header.innerHTML=`<a class="workspace-brand" href="#home">${icon('global')}<b>Frame<span>CAE</span></b></a><span class="brand-caption">空间刚架分析工作台</span><div class="header-end"><span class="local-dot"></span>本地工作空间<span class="unit-chip">SI 单位制</span></div>`;
  const sidebar=document.createElement('aside');sidebar.id='workspaceSidebar';
  const nav=(key,label)=>`<button data-module="${key}" class="nav-item" aria-label="${label}" title="${label}"><span class="nav-icon">${icon(key)}</span><span class="nav-text">${label}</span></button>`;
  sidebar.innerHTML=`<nav aria-label="分析工作流程">${nav('home','工作台概览')}<p class="nav-label">建立模型</p>${nav('global',modules.global.title)}<p class="nav-label">结果与校核</p>${['forces','strength','stability','fullStress'].map(key=>nav(key,modules[key].title)).join('')}<p class="nav-label">深入分析</p>${nav('local',modules.local.title)}</nav><div class="sidebar-note">${icon('global')}<strong>同一模型，连续分析</strong><p>整体计算完成后，结果将用于各项校核与局部分析。</p><span>m · N · Pa</span></div>`;header.after(sidebar);
  hub.innerHTML=`<div class="home-heading"><div><p class="eyebrow">FRAMECAE / 分析工作台</p><h1 tabindex="-1">从整体结构，到关键节点</h1><p class="home-lead">一个模型，连贯完成建模、计算与校核。</p></div><span class="model-state" data-model-state></span></div>
    <div class="workflow-strip" aria-label="推荐分析顺序">${[['global','建立模型','结构 · 支座 · 荷载'],['forces','查看响应','位移 · 杆件内力'],['strength','完成校核','强度 / 稳定'],['local','深入节点','应力 · 网格收敛']].map(([key,title,detail],i)=>`<button data-module="${key}" class="workflow-step"><span>${i+1}</span><div><strong>${title}</strong><small>${detail}</small></div>${icon('arrow')}</button>`).join('')}</div>
    <div class="start-card"><div class="start-copy"><span class="section-kicker">下一步 · 准备整体模型</span><h2 id="startTitle">搭建结构，开始分析</h2><p id="startDescription">定义杆件、材料与荷载，<br>一次整体计算，为后续分析提供依据。</p><div class="start-actions"><button class="primary-action" data-module="global" id="startModel">进入建模 ${icon('arrow')}</button><button class="quiet-action" id="homeImport">${icon('upload')} 导入模型</button><button class="quiet-action" data-module="global" id="homeEdit" hidden>编辑模型</button></div></div><div class="model-preview"><div class="preview-label"><span class="local-dot"></span>当前模型<span class="preview-kind">空间杆系</span></div><div id="homeStructure"></div><div id="homeModelStats" class="model-stats"></div></div></div>
    <div class="section-heading"><div><h2>分析与校核 <span class="section-count">5 个模块</span></h2><p id="analysisGuidance">先完成整体计算，再按需要选择分析模块。</p></div><span class="section-note">共用整体模型 · 按需开展</span></div><div class="analysis-grid">${['forces','strength','stability','local','fullStress'].map(key=>`<button class="analysis-card" data-module="${key}"><div class="card-top"><span class="card-icon">${icon(key)}</span><span class="module-code">模块 ${modules[key].code}</span></div><h3>${modules[key].title}</h3><p>${modules[key].brief}</p><div class="card-bottom"><span data-analysis-state></span>${icon('arrow')}</div></button>`).join('')}</div><p class="workspace-tip">${icon('check')} 修改结构或荷载后，重新计算即可更新分析依据。</p>`;
  const heading=document.createElement('section');heading.id='workspaceHeading';heading.innerHTML='<div><p class="eyebrow" id="workflowBreadcrumb"></p><h1 id="workflowTitle" tabindex="-1"></h1><p id="workflowDescription"></p></div><span class="model-state" data-model-state></span>';main.before(heading);
  const statusEl=$('#status'),footer=document.createElement('footer');footer.id='workspaceStatus';footer.setAttribute('role','status');footer.setAttribute('aria-live','polite');footer.innerHTML='<span class="status-dot"></span>';footer.append(statusEl);document.body.append(footer);
  const top=editor.querySelector('.top');top.classList.add('workspace-actions');
  const fileMenu=document.createElement('details');fileMenu.className='file-menu';fileMenu.innerHTML='<summary>文件</summary><div class="file-menu-items"></div>';
  ['import','exportModel','exportResult','exportCsv','default'].forEach(id=>fileMenu.querySelector('div').append($('#'+id)));top.prepend(fileMenu);
  const confirmButton=$('#builderConfirmModel');top.append(confirmButton);
  const headingActions=document.createElement('div');headingActions.className='heading-actions';headingActions.append(heading.querySelector('[data-model-state]'),fileMenu);heading.append(headingActions);
  const guide=document.createElement('div');guide.id='moduleGuide';guide.innerHTML=`<span class="guide-icon">${icon('global')}</span><div><strong id="guideTitle"></strong><p id="guideCopy"></p></div><button id="guideNext" class="secondary"></button>`;heading.after(guide);
  ['solve','loadT','returnGlobal'].forEach(id=>$('#'+id).hidden=true);
  $('#import').textContent='导入模型 JSON';$('#default').textContent='新建空白模型';$('#verification').remove();
  fileMenu.addEventListener('click',event=>{if(event.target.closest('button'))fileMenu.open=false;});
  document.addEventListener('click',event=>{if(!fileMenu.contains(event.target))fileMenu.open=false;});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')fileMenu.open=false;});
  const tables=$('#tables'),builder=$('#visualBuilderSettings'),selfWeight=$('#selfWeightSettings'),assembly=$('#assemblySettings');
  const sectionMap={strength:$('#strengthCheckSettings'),stability:$('#stabilityCheckSettings'),forces:$('#internalForceSettings'),local:$('#genericLocalSettings'),fullStress:$('#fullStressSettings')};
  // Keep the original form controls and handlers, ordered by the actual local-analysis workflow.
  const localPanel=sectionMap.local,localGrid=localPanel.querySelector('.local-grid');
  localPanel.querySelector('summary').textContent='节点局部应力分析';
  const localStep=(number,title)=>{const section=document.createElement('section');section.className='local-workflow-step';section.innerHTML=`<h3><span>${number}</span>${title}</h3>`;localPanel.append(section);return section;};
  const chooseStep=localStep('1','选择分析节点'),meshStep=localStep('2','连接构造与网格');
  const chooseGrid=document.createElement('div');chooseGrid.className='local-grid';chooseGrid.append($('#genericNode').closest('label'));chooseStep.append(chooseGrid);
  const chooseActions=document.createElement('div');chooseActions.className='actions';chooseActions.append($('#autoGeneric'),$('#selectedGeneric'));chooseStep.append(chooseActions,$('#genericLocalHint'));
  meshStep.append($('#weldedConnectionSettings'),localGrid);
  const geometryHelp=[...localPanel.children].find(el=>el.matches('p.help'));if(geometryHelp)meshStep.append(geometryHelp);
  const runActions=document.createElement('div');runActions.className='actions';runActions.append($('#runGeneric'));meshStep.append(runActions);$('#runGeneric').textContent='计算局部应力';
  const convergenceControls=$('#genericCoarseSize').closest('.local-grid').parentElement;
  const convergenceStep=document.createElement('details');convergenceStep.className='local-workflow-step';convergenceStep.innerHTML='<summary>3　网格收敛验证</summary>';convergenceStep.append(convergenceControls);localPanel.append(convergenceStep);$('#runGenericConvergence').textContent='开始网格收敛验证';
  [...localPanel.children].filter(el=>el.matches('.actions')&&!el.children.length).forEach(el=>el.remove());
  const tabs=document.createElement('div');tabs.id='modelEditorTabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','模型编辑方式');
  tabs.innerHTML=['图形建模','参数表格','自重与装配','AI 建模','图像建模'].map((name,i)=>`<button role="tab" id="modelTab${i}" aria-selected="${i===0}" data-editor="${i}">${name}</button>`).join('');top.after(tabs);
  const aiPanel=$('#aiModelingAssistant');
  const imagePanel=$('#calibratedImageModeling');
  aiPanel?.addEventListener('click',event=>{if(event.target.closest('#aiPreviewDraft,#aiApplyDraft')){editorMode=0;refreshSections();window.frameCAERefreshVisualBuilder?.();}});
  let active='home',editorMode=0;
  const shown=(el,visible,display='')=>{if(el){el.hidden=!visible;el.style.display=visible?display:'none';}};
  const ready=()=>Boolean(window.frameCAEHasConfirmedModel?.());
  const keyboardTabs=list=>list.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;const items=[...list.querySelectorAll('[role=tab]')],index=items.indexOf(document.activeElement);if(index<0)return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowRight'?1:-1)+items.length)%items.length;items[next].click();items[next].focus();});
  tabs.addEventListener('click',event=>{const button=event.target.closest('[data-editor]');if(button){editorMode=Number(button.dataset.editor);refreshSections();window.frameCAERefreshVisualBuilder?.();}});keyboardTabs(tabs);
  builder.querySelector('summary').textContent='三维结构模型';builder.querySelector('p.help').textContent='新建杆件后拖动节点调整位置。选择节点，再设置支座或荷载。';
  const tools=builder.querySelector('.builder-tools'),pieces=[[],[],[],[]];let piece=0;
  [...tools.children].forEach(el=>{if(el.tagName==='HR'){piece++;el.remove();}else pieces[Math.min(piece,3)].push(el);});
  const toolTabs=document.createElement('div');toolTabs.className='builder-tabs';toolTabs.setAttribute('role','tablist');toolTabs.setAttribute('aria-label','建模工具');toolTabs.innerHTML=['几何','支座','荷载'].map((name,i)=>`<button role="tab" id="builderToolTab${i}" aria-controls="builderToolPanel${i}" aria-selected="${i===0}" data-tool="${i}">${name}</button>`).join('');tools.prepend(toolTabs);
  const groups=pieces.filter((_,i)=>i!==1).map((nodes,i)=>{const div=document.createElement('div');div.className='builder-tool-panel';div.id='builderToolPanel'+i;div.setAttribute('role','tabpanel');div.setAttribute('aria-labelledby','builderToolTab'+i);nodes.forEach(el=>div.append(el));tools.append(div);return div;});
  const constraints=document.createElement('details');constraints.innerHTML='<summary>几何约束</summary>';pieces[1].forEach(el=>{if(el.tagName!=='STRONG')constraints.append(el);else el.remove();});groups[0].append(constraints);
  const display=document.createElement('details');display.innerHTML='<summary>网格与显示</summary>';[...groups[0].children].filter(el=>el.tagName==='LABEL').forEach(el=>display.append(el));display.append($('#builderResetView'));groups[0].append(display);
  const more=document.createElement('details');more.innerHTML='<summary>删除与清空</summary>';['builderDeleteBeam','builderDeleteNode','builderClear'].forEach(id=>more.append($('#'+id)));groups[0].append(more);tools.append($('#builderSelection'));
  const selectTool=index=>{groups.forEach((group,i)=>shown(group,i===index));toolTabs.querySelectorAll('button').forEach((button,i)=>{button.setAttribute('aria-selected',String(i===index));button.tabIndex=i===index?0:-1;});};
  toolTabs.addEventListener('click',event=>{const button=event.target.closest('[data-tool]');if(button)selectTool(Number(button.dataset.tool));});keyboardTabs(toolTabs);selectTool(0);
  ['builderNewBeam','builderApplyBC','builderApplyLoad'].forEach(id=>$('#'+id).classList.add('tool-primary'));$('#builderNewBeam').textContent='＋ 新建杆件';$('#builderApplyBC').textContent='应用支座约束';$('#builderApplyLoad').textContent='应用节点荷载';
  // Three-step manual builder; existing AI panel and events are untouched.
  const manual=window.frameCAEManualBuilder;
  const create=(tag,html,cls)=>{const e=document.createElement(tag);e.innerHTML=html;if(cls)e.className=cls;return e;};
  toolTabs.querySelectorAll('button').forEach((b,i)=>b.textContent=['1 搭结构','2 设支座','3 加荷载'][i]);
  builder.querySelector('p.help').textContent='选起点，按方向或终点坐标接杆；斜杆可直接输入 XYZ，无需拖动。';
  const canvasWrap=builder.querySelector('.builder-canvas-wrap');
  const canvasArea=create('div','','easy-canvas-area');canvasWrap.before(canvasArea);
  const canvasTools=create('div','<button id="easyFitView" class="secondary">适配模型</button>','easy-canvas-tools');
  canvasTools.append($('#builderResetView'),$('#builderGridVisible').closest('label'));canvasArea.append(canvasTools,canvasWrap);
  $('#easyFitView').onclick=()=>manual.fitView();
  const nodeChoice=create('label','当前节点 <select id="easyNode" aria-label="当前节点"></select>','easy-node');
  toolTabs.after(nodeChoice);nodeChoice.querySelector('select').onchange=e=>manual.selectNode(e.target.value);
  const setup=create('div','<strong>先设置材料与圆管</strong><p class="help">默认值可修改；E 为弹性模量。</p><label>外径 (mm)<input id="easyD" type="number" value="100" min="0.1"></label><label>壁厚 (mm)<input id="easyT" type="number" value="5" min="0.1"></label><label>E (GPa)<input id="easyE" type="number" value="210" min="0.1"></label><p class="help">泊松比 0.3；密度 7850 kg/m³。适用于钢材，其他材料请用参数表格。</p><button id="easyPrepare">采用以上参数</button>','easy-setup');
  const geometry=create('div','<label>终点方式<select id="easyEnd"><option value="">按方向与长度延伸</option></select></label><div id="easyExtend"><label>方向<select id="easyDirection"><option value="xp">沿 +X</option><option value="xn">沿 −X</option><option value="yp">沿 +Y</option><option value="yn">沿 −Y</option><option value="zp">沿 +Z（向上）</option><option value="zn">沿 −Z（向下）</option></select></label><label>杆长 (m)<input id="easyLength" type="number" value="2" min="0.001" step="0.1"></label></div><div id="easyCoordinates" hidden><p class="help">终点的全局绝对坐标，单位 m；不受网格吸附限制。</p><label>X (m)<input id="easyEndX" type="number" step="any" value="0"></label><label>Y (m)<input id="easyEndY" type="number" step="any" value="0"></label><label>Z (m)<input id="easyEndZ" type="number" step="any" value="0"></label></div><div class="easy-properties"><label>材料<select id="easyMaterial"></select></label><label>截面<select id="easySection"></select></label></div><p class="help">从当前节点接杆；空模型从原点开始。终点重合时自动共用节点。</p><button id="easyAddBeam">＋ 添加杆件</button>','easy-geometry');
  groups[0].prepend(setup,geometry);$('#builderNewBeam').hidden=true;
  $('#easyPrepare').onclick=()=>manual.prepareTube({diameter:$('#easyD').value,thickness:$('#easyT').value,elasticModulus:$('#easyE').value});
  $('#easyAddBeam').onclick=()=>manual.addDirected({direction:$('#easyDirection').value,length:$('#easyLength').value,endNode:$('#easyEnd').value,endPosition:{x:$('#easyEndX').value,y:$('#easyEndY').value,z:$('#easyEndZ').value},material:$('#easyMaterial').value,section:$('#easySection').value});
  const updateEndMode=()=>{const mode=$('#easyEnd').value;$('#easyExtend').hidden=Boolean(mode);$('#easyCoordinates').hidden=mode!=='coordinates';};
  $('#easyEnd').onchange=updateEndMode;
  const presets=create('div','<p class="help">选择节点后，一键设置常用支座。</p><button data-support="fixed">固定支座</button><button data-support="pinned" class="secondary">铰支座</button><p class="help">固定：限制全部平动与转动。<br>铰支：限制三个方向平动，允许转动。</p>','easy-presets');
  groups[1].prepend(presets);const bcAdvanced=create('details','<summary>自定义约束 / 指定位移</summary>','easy-advanced');
  groups[1].querySelectorAll('label').forEach(e=>bcAdvanced.append(e));bcAdvanced.append($('#builderApplyBC'));groups[1].append(bcAdvanced);
  presets.querySelectorAll('button').forEach(button=>button.onclick=()=>{const fixed=button.dataset.support==='fixed';for(const f of ['ux','uy','uz','rx','ry','rz']){const c=$('#builderBC'+f),v=$('#builderBC'+f+'Value');c.checked=fixed||f[0]==='u';v.value='0';v.disabled=!c.checked;}$('#builderApplyBC').click();});
  groups[1].querySelectorAll('.builder-key').forEach(e=>bcAdvanced.append(e));
  const moments=create('details','<summary>附加力矩 (N·m)</summary>','easy-advanced');
  for(const f of ['Mx','My','Mz'])moments.append($('#builderLoad'+f).closest('label'));
  groups[2].insertBefore(moments,$('#builderApplyLoad').parentElement);
  for(const [f,label] of [['Fx','X 方向力 (N)'],['Fy','Y 方向力 (N)'],['Fz','Z 方向力 (N)']]){const input=$('#builderLoad'+f),parent=input.closest('label');parent.firstChild.textContent=label+' ';}
  groups[2].querySelectorAll('.builder-key').forEach(e=>e.hidden=true);
  groups[2].prepend(create('p','输入全局方向的力；向下的力填负 Fz。1 kN = 1000 N。','help'));
  $('#builderApplyLoad').textContent='保存节点荷载';$('#builderClearBC').textContent='移除支座';$('#builderClearLoad').textContent='清除荷载';
  const updateEasy=()=>{
    const s=manual.snapshot(),select=$('#easyNode'),oldEnd=$('#easyEnd').value;
    select.replaceChildren(new Option(s.nodes.length?'请选择节点':'原点 (0, 0, 0) — 添加第一根杆',''),...s.nodes.map(n=>new Option(`N${n.id} · (${n.x}, ${n.y}, ${n.z}) m`,String(n.id))));select.value=s.selectedNode===null?'':String(s.selectedNode);
    $('#easyEnd').replaceChildren(new Option('按方向与长度延伸',''),new Option('指定终点坐标（斜杆）','coordinates'),...s.nodes.filter(n=>n.id!==s.selectedNode).map(n=>new Option(`连接到 N${n.id}`,String(n.id))));if([...$('#easyEnd').options].some(o=>o.value===oldEnd))$('#easyEnd').value=oldEnd;updateEndMode();
    for(const [id,rows,prefix] of [['easyMaterial',s.materials,'材料'],['easySection',s.sections,'截面']]){const el=$('#'+id),old=el.value;el.replaceChildren(...rows.map(r=>new Option(`${prefix} ${r.id}`,String(r.id))));if([...el.options].some(o=>o.value===old))el.value=old;}
    setup.hidden=Boolean(s.materials.length&&s.sections.length);geometry.hidden=!setup.hidden;
    presets.querySelectorAll('button').forEach(b=>b.disabled=s.selectedNode===null);
    const hasMoment=['Mx','My','Mz'].some(f=>Number($('#builderLoad'+f).value)!==0);if(hasMoment)moments.open=true;
  };
  window.addEventListener('framecae:selection',updateEasy);updateEasy();
  const foldLineLoads=()=>{const q=$('#builderMemberLoads');if(!q||q.closest('.easy-line-loads'))return;const fold=create('details','<summary>杆件均布荷载 (N/m)</summary>','easy-advanced easy-line-loads');q.before(fold);fold.append(q);lineObserver.disconnect();};
  const lineObserver=new MutationObserver(foldLineLoads);lineObserver.observe(groups[2],{childList:true});foldLineLoads();


  selfWeight.open=true;assembly.open=false;[$('#selfWeightHint'),$('#assemblyHint')].forEach(el=>el.textContent=el.textContent.replace('从表格计算','确认并计算'));
  const prerequisite=document.createElement('div');prerequisite.id='modulePrerequisite';prerequisite.innerHTML=`<span class="prerequisite-icon">${icon('global')}</span><h2>先完成整体模型计算</h2><p>这个模块将使用已确认模型的结构、荷载与计算结果。<br>完成建模并点击“确认并计算”，即可继续。</p><button data-module="global">去建模与计算 ${icon('arrow')}</button>`;editor.append(prerequisite);
  const empty=document.createElement('div');empty.id='viewerEmpty';empty.innerHTML=`${icon('global')}<h3>计算结果将在这里呈现</h3><p>完成左侧模型设置，点击“确认并计算”。</p><span>三维变形 · 节点位移 · 支座反力</span>`;viewer.append(empty);
  const resultDetails=document.createElement('details');resultDetails.id='resultDetails';resultDetails.innerHTML='<summary>计算结果与数值明细</summary>';$('#results').before(resultDetails);resultDetails.append($('#results'));
  const chartDetails=document.createElement('details');chartDetails.id='memberChartDetails';chartDetails.innerHTML='<summary>杆件沿程曲线</summary>';viewer.append(chartDetails);chartDetails.append(viewer.querySelector('.member-toolbar'),$('#memberDiagram'));chartDetails.addEventListener('toggle',()=>{if(chartDetails.open)drawMemberDiagram();});
  const next=document.createElement('div');next.id='nextAnalysis';next.innerHTML=`<div>${icon('check')}<span>整体计算已完成<strong>下一步，查看结构响应</strong></span></div><button data-module="forces">查看位移与内力 ${icon('arrow')}</button>`;editor.append(next);
  function refreshSections(){
    const confirmed=ready(),global=active==='global';
    document.body.dataset.manualBuilding=String(global&&editorMode===0);
    shown(tabs,global,'flex');shown(builder,global&&editorMode===0);shown(tables,global&&editorMode===1);
    shown(selfWeight,global&&editorMode===2);shown(assembly,global&&editorMode===2);
    shown(aiPanel,global&&editorMode===3);if(aiPanel)aiPanel.open=true;
    shown(imagePanel,global&&editorMode===4);if(imagePanel)imagePanel.open=true;
    tabs.querySelectorAll('button').forEach((button,i)=>{button.setAttribute('aria-selected',String(i===editorMode));button.tabIndex=i===editorMode?0:-1;});
    [...editor.children].filter(el=>el.tagName==='P').forEach(el=>shown(el,false));shown($('#confirmedStructureDetails'),false);
    Object.entries(sectionMap).forEach(([key,panel])=>shown(panel,confirmed&&active===key));
    shown(prerequisite,!global&&active!=='home'&&!confirmed);shown(next,false);
    viewer.dataset.ready=String(confirmed);shown(empty,!confirmed);shown(resultDetails,confirmed&&active!=='forces');shown(chartDetails,confirmed&&['global','forces'].includes(active));shown($('#convergence'),confirmed&&active==='local'&&Boolean(convergenceResult?.samples?.length));
    // Files and exports remain reachable while inspecting any result module.
    ['import','exportModel','exportResult','exportCsv','default'].forEach(id=>shown($('#'+id),true));
    ['exportResult','exportCsv'].forEach(id=>$('#'+id).disabled=!confirmed);
    shown(guide,active!=='home','flex');
    const tips={global:['准备结构与荷载','图形建模或表格编辑 → 确认并计算 → 查看结构响应','查看位移与内力','forces'],forces:['查看结构响应','先观察变形，再切换弯矩、扭矩与轴力，定位关键杆件。','去强度校核','strength'],strength:['校核截面承载能力','设置材料强度，比较四种理论下的危险截面与利用率。','去稳定校核','stability'],stability:['检查受压杆件','设置计算长度，检查临界力与稳定利用率。','去满应力计算','fullStress'],fullStress:['调整刚架杆件尺寸','固定总体积，逐轮重算强度、稳定与截面。','去节点分析','local'],local:['深入关键连接节点','选择节点 → 设置焊缝与网格 → 计算应力 → 验证收敛','返回整体模型','global']};
    if(active!=='home'){
      const tip=tips[active];$('#guideTitle').textContent=!confirmed&&active!=='global'?'需要整体计算结果':tip[0];$('#guideCopy').textContent=!confirmed&&active!=='global'?'先确认结构、支座与荷载，完成整体计算后即可继续。':tip[1];
      if(global&&confirmed){$('#guideTitle').textContent='整体计算已完成';$('#guideCopy').textContent='查看位移与内力，检查结构响应，再选择需要的校核。';}
      $('#guideNext').textContent=confirmed?tip[2]:'去建模与计算';$('#guideNext').dataset.module=confirmed?tip[3]:'global';shown($('#guideNext'),active!=='global'||confirmed);guide.querySelector('.guide-icon').innerHTML=icon(active);
    }
  }
  let lastPreview='';
  function preview(){
    const model=typeof data==='object'?data:{},nodes=model.nodes||[],elements=model.elements||[],constraints=model.constraints||[];
    const signature=JSON.stringify([nodes,elements,constraints,view.yaw,view.pitch]);if(signature===lastPreview)return;lastPreview=signature;
    $('#homeModelStats').innerHTML=`<span><b>${nodes.length}</b> 节点</span><span><b>${elements.length}</b> 杆件</span><span><b>${new Set(constraints.map(item=>item.node)).size}</b> 约束节点</span>`;
    const points=nodes.map(n=>({id:Number(n.id),...window.FrameCAEModelView.projectOffset([Number(n.x),Number(n.y),Number(n.z)],view)})).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
    if(!points.length){$('#homeStructure').innerHTML='<p class="preview-empty">导入或创建模型后，在这里查看结构</p>';return;}
    const xs=points.map(p=>p.x),ys=points.map(p=>p.y),lowX=Math.min(...xs),highX=Math.max(...xs),lowY=Math.min(...ys),highY=Math.max(...ys),scale=Math.min(280/Math.max(highX-lowX,.1),150/Math.max(highY-lowY,.1));
    const mapped=new Map(points.map(p=>[p.id,{x:220+(p.x-(lowX+highX)/2)*scale,y:110+(p.y-(lowY+highY)/2)*scale}]));
    const lines=elements.map(e=>{const a=mapped.get(Number(e.start)),b=mapped.get(Number(e.end));return a&&b?`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`:'';}).join(''),dots=[...mapped.entries()].map(([id,p])=>`<circle cx="${p.x}" cy="${p.y}" r="3.5"><title>${window.FrameCAEModelView.nodeLabel(id)}</title></circle>`).join('');
    const labels=nodes.length<=20?[...mapped.entries()].map(([id,p])=>`<text x="${p.x+5}" y="${p.y-6}">${window.FrameCAEModelView.nodeLabel(id)}</text>`).join(''):'';
    const axes=[[1,0,0,'X','#d33c4a'],[0,1,0,'Y','#1b9b61'],[0,0,1,'Z','#2871cf']].map(([x,y,z,label,color])=>{
      const p=window.FrameCAEModelView.projectOffset([x,y,z],view),end={x:42+30*p.x,y:181+30*p.y};
      return `<g stroke="${color}" fill="${color}"><line x1="42" y1="181" x2="${end.x}" y2="${end.y}"/><text x="${end.x+4}" y="${end.y-4}" stroke="none">+${label}</text></g>`;
    }).join('');
    $('#homeStructure').innerHTML=`<svg viewBox="0 0 440 220" role="img" aria-label="当前模型的三维杆系预览"><g stroke="#218781" stroke-width="2.5" stroke-linecap="round">${lines}</g><g fill="#fff" stroke="#218781" stroke-width="1.8">${dots}</g><g fill="#405b73" font-size="10">${labels}</g><g font-size="10" stroke-width="1.5">${axes}</g></svg>`;
  }
  function updateState(){
    const confirmed=ready(),message=statusEl.textContent.trim();
    document.querySelectorAll('[data-model-state]').forEach(el=>{el.textContent=confirmed?'整体模型已计算':confirmButton.disabled?'正在计算':'模型待计算';el.classList.toggle('is-ready',confirmed);});
    document.querySelectorAll('[data-analysis-state]').forEach(el=>{el.textContent=confirmed?'进入分析':'需整体计算';el.classList.toggle('is-ready',confirmed);});
    $('#startTitle').textContent=confirmed?'计算已完成，查看结构响应':'搭建结构，开始分析';
    $('#startDescription').textContent=confirmed?'先检查位移与杆件内力，再根据关键部位开展强度、稳定和局部应力分析。':'定义杆件、材料与荷载，一次整体计算，为后续分析提供依据。';
    hub.querySelector('.section-kicker').textContent=confirmed?'下一步 · 检查结构响应':'下一步 · 准备整体模型';
    const target=confirmed?'forces':'global',label=confirmed?'查看位移与内力':'进入建模';
    if($('#startModel').dataset.module!==target||$('#startModel').textContent.trim()!==label){$('#startModel').dataset.module=target;$('#startModel').innerHTML=`${label} ${icon('arrow')}`;}
    shown($('#homeEdit'),confirmed,'inline-flex');shown($('#homeImport'),!confirmed,'inline-flex');
    $('#analysisGuidance').textContent=confirmed?'整体结果已就绪，强度、稳定与节点分析可按需开展。':'先完成整体计算，再按需要选择分析模块。';
    hub.querySelectorAll('.workflow-step').forEach((button,i)=>{button.classList.toggle('is-current',i===(confirmed?1:0));button.classList.toggle('is-done',confirmed&&i===0);});
    footer.classList.toggle('is-working',/正在|求解中|计算中/.test(message));footer.classList.toggle('is-error',/失败|错误|需要修正/.test(message));preview();refreshSections();
  }
  function navigate(module,focus=true){
    if(module!=='home'&&!modules[module])return;active=module;document.body.dataset.module=module;
    if(module==='home'){window.frameCAEOpenHome();window.frameCAEActiveModule='home';}else{
      window.frameCAEOpenModule(module);$('#workflowTitle').textContent=modules[module].title;$('#workflowDescription').textContent=modules[module].brief;$('#workflowBreadcrumb').textContent=`工作台 / ${module==='global'?'建立模型':module==='local'?'深入分析':'结果与校核'} / ${modules[module].code}`;
      displayMode=module==='local'&&localResult?'local':'global';
    }
    shown(heading,module!=='home','flex');sidebar.querySelectorAll('[data-module]').forEach(button=>{if(button.dataset.module===module)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});updateState();
    requestAnimationFrame(()=>{draw();if(module==='global')window.frameCAERefreshVisualBuilder?.();});
    if(focus)(module==='home'?hub.querySelector('h1'):$('#workflowTitle')).focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
  }
  [sidebar,hub,prerequisite,next,guide].forEach(root=>root.addEventListener('click',event=>{const button=event.target.closest('button[data-module]');if(button&&root.contains(button))navigate(button.dataset.module);}));
  fileMenu.addEventListener('click',event=>{if(event.target.closest('#import,#default,#verification')&&active!=='global')navigate('global');},true);
  header.querySelector('a').onclick=event=>{event.preventDefault();navigate('home');};$('#homeImport').onclick=()=>{navigate('global');$('#import').click();};
  new MutationObserver(updateState).observe(statusEl,{childList:true,characterData:true,subtree:true});
  new MutationObserver(updateState).observe($('#builderStatus'),{childList:true,characterData:true,subtree:true});
  window.addEventListener('framecae:model-state',updateState);
  new MutationObserver(()=>{if(active==='local')refreshSections();}).observe($('#results'),{childList:true,characterData:true,subtree:true});
  navigate('home',false);
})();
