/* Shared result workspace. All charts use solver stations and returned checks. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = n => Number.isFinite(n) ? n : 0;
  const fmt = n => Number.isFinite(n) ? Number(n.toPrecision(4)).toString() : '—';
  const riskColor = n => !Number.isFinite(n) ? '#aab5c5' : n > 1 ? '#dc4d61' : n > .8 ? '#e6a039' : '#37958c';
  function forceChart(element, mode) {
    const stations = element?.stations || [];
    if (!stations.length) return '<p class="vw-placeholder">当前杆件没有沿程结果。</p>';
    const components = mode === 'axial' ? [[0,'N','#337cca']] : mode === 'torsion' ? [[3,'T','#22a17e']] : [[4,'My','#a15ab6'],[5,'Mz','#209fbc']];
    const length = stations.reduce((m,s) => Math.max(m,num(s.position)),1e-12);
    const values = stations.flatMap(s => components.map(([i]) => num(s.forces[i])/1000));
    const low = values.reduce((m,n) => Math.min(m,n),0), high = values.reduce((m,n) => Math.max(m,n),0);
    const span = Math.max(high-low,Math.abs(high)*.2,Math.abs(low)*.2,1e-6);
    const bottom=(high+low)/2-span*.6,top=(high+low)/2+span*.6;
    const x = n => 74+num(n)/length*644, y = n => 234-(n-bottom)/(top-bottom)*200;
    const grid = Array.from({length:5},(_,i) => {const n=bottom+(top-bottom)*i/4;return `<line x1="74" x2="718" y1="${y(n)}" y2="${y(n)}" stroke="#e8edf4"/><text x="63" y="${y(n)+4}" text-anchor="end">${fmt(n)}</text>`;}).join('');
    const paths = components.map(([i,name,color]) => `<path d="${stations.map((s,j) => `${j?'L':'M'}${x(s.position)},${y(num(s.forces[i])/1000)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.6"/><text x="${570+i*23}" y="21" fill="${color}">${name}</text>`).join('');
    return `<svg viewBox="0 0 760 280" role="img" aria-label="E${esc(element.id)} ${mode==='bending'?'My / Mz':mode==='torsion'?'T':'N'} 沿程曲线"><g font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="12" fill="#71829a">${grid}<line x1="74" x2="718" y1="${y(0)}" y2="${y(0)}" stroke="#aab8cc" stroke-dasharray="4 4"/>${paths}<text x="74" y="21">${mode==='axial'?'轴力 / kN':'力矩 / kN·m'}</text><text x="74" y="263">0</text><text x="718" y="263" text-anchor="end">${fmt(length)}</text><text x="396" y="263" text-anchor="middle">局部 x / m</text></g></svg>`;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {forceChart,riskColor};
  if (typeof document === 'undefined') return;
  const $ = s => document.querySelector(s), viewer = $('#viewer');
  if (!viewer) return;
  const sheet = document.createElement('link'); sheet.rel='stylesheet';sheet.href='/visual-workbench.css';document.head.append(sheet);
  const header = document.createElement('div');header.id='visualHeading';
  header.innerHTML='<div><span class="vw-kicker">RESULT VIEW</span><h2 id="visualTitle"></h2><p id="visualDescription"></p></div><div class="vw-actions"><button class="secondary" id="visualExpand" aria-pressed="false">扩大图区</button><button class="secondary" id="visualExport">导出分析图</button></div>';
  viewer.prepend(header);
  const stats = document.createElement('div');stats.id='visualStats';header.after(stats);
  const camera = document.createElement('div');camera.id='visualCamera';camera.innerHTML='<div class="vw-viewgroup" role="group" aria-label="图形视角"><button data-view="iso" aria-pressed="true">三维</button><button data-view="top" aria-pressed="false">俯视 XY</button><button data-view="front" aria-pressed="false">正视 XZ</button><button data-view="side" aria-pressed="false">侧视 YZ</button></div><button id="visualFit" class="secondary">适配视图</button><span>拖动旋转 · 滚轮缩放</span>';
  $('#scene').before(camera);
  const caption = document.createElement('div');caption.id='visualCaption';$('#scene').after(caption);
  const localNotice=document.createElement('p');localNotice.id='visualLocalNotice';stats.after(localNotice);
  caption.after($('#localReport'));
  const checks = document.createElement('div');checks.id='visualChecks';caption.after(checks);
  for (const id of ['strengthSummary','stabilitySummary']) {
    let summary=$('#'+id);
    if(!summary){summary=document.createElement('div');summary.id=id;}
    checks.append(summary);
  }
  const notice=document.createElement('p');notice.id='visualCheckNotice';checks.prepend(notice);
  const meshLabel=document.createElement('label');meshLabel.innerHTML='<input id="visualMesh" type="checkbox"> 网格边线';meshLabel.className='vw-localMesh';$('#localCloudBar').append(meshLabel);
  $('#visualMesh').onchange=()=>{window.frameCAELocalCloudOptions.meshEdges=$('#visualMesh').checked;draw();};
  const force = document.createElement('section');force.id='visualForce';force.innerHTML='<div class="vw-chartheading"><h3 id="visualForceTitle">选中杆件沿程曲线</h3><span>沿用求解器截面站点</span></div><div id="visualForceCurve"></div>';checks.after(force);
  const state = {strength:null,stability:null,theory:'mises',selected:null,camera:'iso'};
  const metadata = {
    global:['整体结构响应','连续梁位移曲线 · 变形与原始构形对照'],
    forces:['杆件内力分析','三维内力分布 + 选中杆件沿程曲线'],
    strength:['截面强度结果','危险杆件定位 · 四种强度理论对比'],
    stability:['受压杆稳定结果','Euler 临界力 · 稳定利用率与控制轴'],
    local:['节点局部应力结果','真实实体网格云图 · 固定表面热点收敛验证']
  };
  const active = () => document.body.dataset.module;
  const signature = () => JSON.stringify(payload());
  const settingsSignature = kind => JSON.stringify([...$('#'+(kind==='strength'?'strengthCheckSettings':'stabilityCheckSettings')).querySelectorAll('input,select')].filter(el=>el.id!=='stabilityShowTension').map(el=>[el.id,el.value,el.type==='checkbox'?el.checked:null]));
  window.addEventListener('framecae:check-result', event => {
    const {kind,answer,theory}=event.detail;
    state[kind]={answer,model:signature(),settings:settingsSignature(kind)};
    if(theory)state.theory=theory;
    decorateResults(kind);refresh();draw();
  });
  window.addEventListener('framecae:strength-theory',event=>{state.theory=event.detail.theory;decorateResults('strength');refresh();draw();});
  function current(kind) {
    const saved=state[kind];return saved && window.frameCAEHasConfirmedModel?.() && saved.model===signature() && saved.settings===settingsSignature(kind);
  }
  function decorateResults(kind) {
    const root=$('#'+kind+'Summary');
    if(kind==='strength'){
      const layout=root.querySelector('.strength-result-layout'),table=layout?.querySelector('.strength-result-card:not(.strength-analysis-card)');
      if(table&&!table.closest('details.vw-details')){const details=document.createElement('details');details.className='vw-details';details.innerHTML='<summary>四种理论数值对照</summary>';details.append(table);layout.append(details);}
    }else{
      const table=root.querySelector('.table-wrap');if(table&&!table.closest('details')){const details=document.createElement('details');details.className='vw-details';details.innerHTML='<summary>逐杆稳定校核明细</summary>';table.before(details);details.append(table);}
    }
    root.querySelectorAll('svg').forEach(svg=>{svg.setAttribute('role','img');if(!svg.getAttribute('aria-label'))svg.setAttribute('aria-label',kind==='strength'?'强度利用率':'受压杆稳定利用率');});
  }
  new MutationObserver(()=>decorateResults('stability')).observe($('#stabilitySummary'),{childList:true});
  const memberSettings=$('#stabilityMemberTable')?.closest('.table-wrap');
  if(memberSettings){const details=document.createElement('details');details.className='vw-details';details.innerHTML='<summary>逐杆端部约束（可选）</summary>';memberSettings.before(details);details.append(memberSettings);}
  const card = (label,value,unit,detail) => `<div class="vw-stat"><span>${esc(label)}</span><strong>${esc(value)}<small>${esc(unit)}</small></strong><p>${esc(detail)}</p></div>`;
  const put = (element,html) => {if(element.innerHTML!==html)element.innerHTML=html;};
  let lastForceResult=null,lastForceKey='';
  function refresh() {
    const m=active(), ready=Boolean(window.frameCAEHasConfirmedModel?.()),meta=metadata[m]||metadata.global;
    $('#visualTitle').textContent=meta[0];$('#visualDescription').textContent=meta[1];
    $('#visualExport').disabled=!ready||(m==='local'&&(!localResult?.result||$('#exportLocalFigure').disabled))||(m==='strength'||m==='stability')&&!current(m);
    $('#strengthSummary').hidden=m!=='strength';$('#stabilitySummary').hidden=m!=='stability';checks.hidden=!['strength','stability'].includes(m)||!ready;
    force.hidden=m!=='forces'||!ready;stats.hidden=m==='local'||!ready;
    localNotice.hidden=m!=='local'||!ready||!localResult?.result;
    if(!localNotice.hidden)localNotice.textContent=$('#localReport .lr-badge').textContent+' · '+$('#localReport .lr-notice').textContent;
    viewer.dataset.visualReady=String(ready&&(m!=='local'||Boolean(localResult?.result)));
    $('#viewerEmpty').dataset.localEmpty=String(ready&&m==='local'&&!localResult?.result);
    if(ready&&m==='local'&&!localResult?.result){$('#viewerEmpty').style.display='flex';$('#viewerEmpty').querySelector('h3').textContent='局部应力云图待计算';$('#viewerEmpty').querySelector('p').textContent='选择节点并计算局部应力，随后查看云图和收敛曲线。';}
    else {$('#viewerEmpty').querySelector('h3').textContent='计算结果将在这里呈现';$('#viewerEmpty').querySelector('p').textContent='完成左侧模型设置，点击“确认并计算”。';if(ready)$('#viewerEmpty').style.display='none';}
    if(!ready)return;
    if(m==='strength'||m==='stability'){
      const saved=state[m],valid=current(m);
      notice.textContent=saved?valid?'颜色按每根杆件的最大利用率绘制。绿色 ≤80%，橙色 80%–100%，红色 >100%；灰色为不参与校核的杆件。':'参数或模型已修改，下方为上次校核结果，请重新计算。':'设置左侧参数并执行校核，即可查看危险杆件、利用率分布与数值对照。';
      notice.className=valid?'':'vw-placeholder';
      let html='';
      if(valid){const a=saved.answer,c=m==='strength'?a.theories[state.theory].critical:a.critical;
        if(c)html=card('控制杆件','E'+c.element,'',m==='strength'?'截面名义强度':'受压杆 Euler 稳定')+card('最大利用率',fmt((m==='strength'?c.utilizations[state.theory]:c.utilization)*100),'%',m==='strength'?state.theory:'控制轴 '+c.governingAxis)+card(m==='strength'?'等效应力':'设计压力',fmt(m==='strength'?c.equivalentStresses[state.theory]/1e6:c.axialForce/1e3),m==='strength'?'MPa':'kN',m==='strength'?'x = '+fmt(c.position)+' m':'沿杆最大压力');
      }
      put(stats,html);caption.textContent=valid?'结构利用率分布 · 原始构形 · 颜色代表每根杆件的控制值':'结构参考视图 · 校核完成后显示利用率分布';
    }else if(m==='global'){
      const peak=result?.summary?.deformation?.curvePeak,elems=result?.elements||[];
      put(stats,card('最大位移',fmt(peak?.magnitude*1000),'mm',peak?'E'+peak.element+' · x='+fmt(peak.position)+' m':'沿梁位移曲线峰值')+card('最大名义应力',fmt(elems.reduce((a,e)=>Math.max(a,num(e.maxNominalStress)),0)/1e6),'MPa','杆件截面应力，不含局部焊缝集中')+card('最大轴力绝对值',fmt(elems.reduce((a,e)=>Math.max(a,num(e.maxAxialForce)),0)/1000),'kN','沿杆截面扫描'));
      const metric=$('#metric').value,labels={displacement:['位移','mm',1000],axial:['轴力绝对值','kN',.001],bending:['弯矩绝对值','kN·m',.001],stress:['名义应力','MPa',1e-6]},[label,unit,factor]=labels[metric]||labels.displacement;
      const max=metric==='displacement'?peak?.magnitude:elems.reduce((a,e)=>Math.max(a,num(e[metric==='axial'?'maxAxialForce':metric==='bending'?'maxBendingMoment':'maxNominalStress'])),0);
      caption.innerHTML=`<span>灰虚线：原始构形 · 彩色：变形构形 · 放大 ${esc($('#scale').value)} 倍</span><span class="vw-scale">${label}　0 <i></i> ${fmt(max*factor)} ${unit}</span>`;
    }else if(m==='forces'){
      const mode=window.frameCAEForceView?.mode||'bending',selected=Number($('#forceSelectedElement').value),key=mode+':'+selected,element=result?.elements?.find(e=>e.id===selected);
      if(result!==lastForceResult||key!==lastForceKey){put($('#visualForceCurve'),forceChart(element,mode));lastForceResult=result;lastForceKey=key;}
      $('#visualForceTitle').textContent=`E${selected} · ${mode==='bending'?'My / Mz 弯矩':mode==='torsion'?'T 扭矩':'N 轴力'}沿程曲线`;
      put(stats,`<div class="vw-forceinfo">${$('#forceSummary').innerHTML}</div>`);
      caption.textContent=mode==='axial'?'蓝色：N > 0 压力 · 红色：N < 0 拉力':mode==='torsion'?'绿色：T > 0 · 橙色：T < 0 · 绕局部 +x 右手定则':'紫色：My · 青色：Mz · 正负位于杆轴两侧';
    }else{caption.textContent='橙色虚线：子模型截断边界 · 空心管端保留实际几何';}
    caption.textContent+=' ｜ 红色箭头：节点力；紫色箭头：均布荷载（大小为相对示意）。';
  }
  function drawUtilization(kind) {
    if(!current(kind)||!result?.nodes?.length)return false;
    setup();const w=canvas.clientWidth,h=canvas.clientHeight,byId=Object.fromEntries(result.nodes.map(n=>[n.id,n.coordinate]));
    const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];result.nodes.forEach(n=>n.coordinate.forEach((v,i)=>{low[i]=Math.min(low[i],v);high[i]=Math.max(high[i],v);}));
    const center=low.map((v,i)=>(v+high[i])/2),span=Math.max(...high.map((v,i)=>v-low[i]),1e-9),pixels=Math.min(w,h)*.60/span*view.zoom;
    const project=point=>{const p=window.FrameCAEModelView.projectOffset(point.map((v,i)=>v-center[i]),view);return {x:w/2+p.x*pixels,y:h/2+p.y*pixels,depth:p.depth};};
    const answer=state[kind].answer,critical=kind==='strength'?answer.theories[state.theory].critical:answer.critical;
    const members=kind==='strength'?answer.memberUtilizations:answer.members;
    const values=new Map(members.map(item=>[item.element,kind==='strength'?item[state.theory]:item.status==='compression'?item.utilization:null]));
    ctx.clearRect(0,0,w,h);ctx.setLineDash([]);ctx.lineCap='round';
    [...result.elements].sort((a,b)=>project(byId[a.start]).depth+project(byId[a.end]).depth-project(byId[b.start]).depth-project(byId[b.end]).depth).forEach(e=>{
      const a=project(byId[e.start]),b=project(byId[e.end]),v=values.get(e.id),selected=critical?.element===e.id;
      if(selected){ctx.strokeStyle='#25384e';ctx.lineWidth=9;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
      ctx.strokeStyle=riskColor(v);ctx.lineWidth=selected?5:4;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
      if(selected||$('#elementLabels').checked){ctx.font='12px Microsoft YaHei,sans-serif';ctx.fillStyle='#25384e';ctx.fillText('E'+e.id+(selected?' · '+fmt(v*100)+'%':''),(a.x+b.x)/2+7,(a.y+b.y)/2-8);}
    });
    result.nodes.forEach(n=>{const p=project(n.coordinate);ctx.fillStyle='#fff';ctx.strokeStyle='#667992';ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(p.x,p.y,3,0,Math.PI*2);ctx.fill();ctx.stroke();if($('#nodeLabels').checked){ctx.fillStyle='#63748c';ctx.fillText('N'+n.id,p.x+5,p.y-5);}});
    if($('#boundaryMarkers')?.checked)window.FrameCAEModelView.drawModelLoads(ctx,result.solvedModel,p=>project([p.x,p.y,p.z]),w,h,{legend:false});
    return true;
  }
  const previousDraw=draw;
  draw=function(){const m=active();if(!(['strength','stability'].includes(m)&&drawUtilization(m)))previousDraw();if(result)window.FrameCAEModelView.drawAxes(ctx,canvas.clientWidth,canvas.clientHeight,view);refresh();};
  function setView(mode){const angles={iso:[-.72,.5],top:[0,Math.PI/2],front:[0,0],side:[Math.PI/2,0]};[view.yaw,view.pitch]=angles[mode];view.zoom=1;state.camera=mode;camera.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===mode)));draw();}
  camera.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>setView(button.dataset.view));
  $('#visualFit').onclick=()=>{view.zoom=1;draw();};
  $('#scene').addEventListener('pointerdown',()=>camera.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed','false')));
  $('#visualExpand').onclick=()=>{const expanded=document.body.classList.toggle('visual-expanded');$('#visualExpand').textContent=expanded?'恢复参数区':'扩大图区';$('#visualExpand').setAttribute('aria-pressed',String(expanded));requestAnimationFrame(draw);};
  $('#visualExport').onclick=()=>{
    refresh();if($('#visualExport').disabled)return;
      const m=active(),images=[...viewer.querySelectorAll('svg')].filter(el=>el.closest('#visualForce,#visualChecks,#localCharts')&&!el.closest('[hidden]')&&el.getBoundingClientRect().width>0);
    if(m==='local'){$('#exportLocalFigure').click();return;}
    const imageHeight=570,total=850+images.length*290;
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${total}" viewBox="0 0 1200 ${total}"><rect width="1200" height="${total}" fill="white"/><g font-family="Microsoft YaHei,Segoe UI,sans-serif" fill="#304763"><text x="45" y="48" font-size="26">FrameCAE · ${esc($('#visualTitle').textContent)}</text><text x="45" y="82" font-size="14">${esc($('#visualDescription').textContent)}</text><foreignObject x="45" y="110" width="1110" height="120"><div xmlns="http://www.w3.org/1999/xhtml" style="font:16px Microsoft YaHei;line-height:1.7">${esc((m==='local'?$('#localReport'):stats).textContent)}</div></foreignObject><image href="${canvas.toDataURL('image/png')}" x="45" y="240" width="1110" height="${imageHeight}" preserveAspectRatio="xMidYMid meet"/><text x="45" y="835" font-size="13">${esc(caption.textContent)}</text>${images.map((el,i)=>{const clone=el.cloneNode(true);clone.setAttribute('x','45');clone.setAttribute('y',String(860+i*290));clone.setAttribute('width','1110');clone.setAttribute('height','270');clone.removeAttribute('style');return clone.outerHTML;}).join('')}</g></svg>`;
    download(`FrameCAE_${m}_分析图.svg`,svg,'image/svg+xml');
  };
  window.addEventListener('framecae-module-change',()=>requestAnimationFrame(()=>{refresh();draw();}));
  window.addEventListener('framecae:model-state',()=>requestAnimationFrame(refresh));
  ['strengthCheckSettings','stabilityCheckSettings'].forEach(id=>$('#'+id).addEventListener('input',()=>{refresh();draw();}));
  new MutationObserver(refresh).observe($('#status'),{childList:true,subtree:true,characterData:true});
  window.frameCAERefreshVisualWorkbench=refresh;
  refresh();
})();
