/* Result charts use the backend's fixed-hotspot metric and decision. */
(() => {
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  const fmt = (n, digits=3) => finite(n) ? n.toPrecision(digits) : '—';
  const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function convergenceView(answer) {
    const samples = Array.isArray(answer?.samples) ? answer.samples : [];
    const tracked = answer?.convergenceMetric === 'trackedHotspotKt';
    const key = tracked ? 'trackedHotspotStressConcentrationFactor' : 'smoothedStressConcentrationFactor';
    const changes = Array.isArray(answer?.relativeChanges) ? answer.relativeChanges : samples.slice(1).map((s,i)=>Math.abs(s[key]-samples[i][key])/Math.max(Math.abs(s[key]),1e-18));
    // A resource stop, unresolved projection or missing decision must never be
    // promoted to convergence merely because two plotted values are close.
    const passed = answer?.converged === true && samples.length >= 3;
    return {samples,changes,key,tracked,passed,label:tracked?'固定表面热点 Kt':'节点平滑峰值 Kt'};
  }
  function chartSvg(answer, changeChart=false) {
    const v = convergenceView(answer), valid = v.samples.filter(s=>finite(s.meshSize)&&finite(s[v.key]));
    if (!valid.length) return '';
    const w=620,h=230,left=64,right=22,top=37,bottom=46;
    const values=changeChart?v.changes.map(x=>finite(x)?x*100:NaN):valid.map(s=>s[v.key]);
    const clean=values.filter(finite); if(!clean.length)return '';
    const xmin=Math.min(...valid.map(s=>s.meshSize)),xmax=Math.max(...valid.map(s=>s.meshSize));
    let ymin=changeChart?0:Math.min(...clean),ymax=changeChart?Math.max(6,...clean):Math.max(...clean);
    const pad=changeChart?0:Math.max((ymax-ymin)*.15,Math.abs(ymax)*.03,1e-6); ymin-=pad;ymax+=pad;
    const x=n=>left+(xmax-n)/Math.max(xmax-xmin,1e-12)*(w-left-right);
    const y=n=>h-bottom-(n-ymin)/Math.max(ymax-ymin,1e-12)*(h-top-bottom);
    let svg=`<svg xmlns="http://www.w3.org/2000/svg" class="lr-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${changeChart?'连续细化相对变化百分比':v.label+'与实际网格尺寸'}"><rect width="620" height="230" fill="#fcfdff"/><text x="16" y="21" fill="#435873" font-size="12">${changeChart?'相邻档相对变化（%）':v.label}</text>`;
    for(let i=0;i<=4;i++){const value=ymin+(ymax-ymin)*i/4,py=y(value);svg+=`<path d="M${left} ${py}H${w-right}" stroke="#e5ebf3"/><text x="${left-8}" y="${py+4}" text-anchor="end" font-size="10" fill="#70819a">${fmt(value,3)}</text>`;}
    svg+=`<path d="M${left} ${top}V${h-bottom}H${w-right}" fill="none" stroke="#b7c7dd"/>`;
    if(changeChart){svg+=`<path d="M${left} ${y(5)}H${w-right}" stroke="#cf8642" stroke-dasharray="5 4"/><text x="${w-right}" y="${y(5)-6}" text-anchor="end" font-size="10" fill="#a86414">5% 判据</text>`;}
    const points=valid.map((s,i)=>({s,i,value:changeChart?(i?v.changes[i-1]*100:NaN):s[v.key]})).filter(p=>finite(p.value));
    svg+=`<polyline points="${points.map(p=>`${x(p.s.meshSize)},${y(p.value)}`).join(' ')}" fill="none" stroke="${changeChart?'#0b8d87':'#7253b7'}" stroke-width="2.5"/>`;
    points.forEach(p=>{svg+=`<circle cx="${x(p.s.meshSize)}" cy="${y(p.value)}" r="4" fill="${changeChart&&p.value>5?'#c45b4f':changeChart?'#0b8d87':'#7253b7'}"><title>第 ${p.i+1} 档：h=${p.s.meshSize} m；${p.value}${changeChart?'%':''}</title></circle>`;});
    valid.forEach(s=>{svg+=`<text x="${x(s.meshSize)}" y="${h-bottom+17}" text-anchor="middle" font-size="10" fill="#71829a">${fmt(s.meshSize,3)}</text>`;});
    svg+=`<text x="${left}" y="${h-9}" font-size="10" fill="#71829a">实际 h（m），由粗到细 →</text></svg>`;
    return svg;
  }
  const helpers = {convergenceView,chartSvg};
  if(typeof module!=='undefined'&&module.exports)module.exports=helpers;
  if(typeof document==='undefined')return;
  const $=s=>document.querySelector(s),viewer=$('#viewer');if(!viewer||$('#localReport'))return;
  const css=document.createElement('link');css.rel='stylesheet';css.href='/local-report.css';document.head.append(css);
  const report=document.createElement('section');report.id='localReport';report.hidden=true;report.setAttribute('aria-label','节点局部分析结果摘要');viewer.prepend(report);
  const cloudBar=document.createElement('div');cloudBar.id='localCloudBar';cloudBar.hidden=true;cloudBar.className='lr-cloudbar';cloudBar.innerHTML='<strong>von Mises 应力云图</strong><label><input id="localPeakMarker" type="checkbox" checked> 峰值位置</label><button id="exportLocalFigure" class="secondary">导出分析图 SVG</button><div id="localStressScale" class="lr-scale"></div>';$('#scene').before(cloudBar);
  const charts=document.createElement('section');charts.id='localCharts';charts.hidden=true;$('#scene').after(charts);
  window.frameCAELocalCloudOptions={peakMarker:true};$('#localPeakMarker').onchange=()=>{window.frameCAELocalCloudOptions.peakMarker=$('#localPeakMarker').checked;draw();};
  let busy=false,task='',started=0,failure='',stale=false,localSignature='',convergenceSignature='';
  const signature=()=>JSON.stringify([payload(),genericLocalSettings()]);
  const convergenceRequestSignature=()=>JSON.stringify([signature(),...['genericCoarseSize','genericFineSize','genericSampleCount','genericMaxDofs'].map(id=>$('#'+id).value)]);
  const card=(label,value,unit,detail)=>`<div class="lr-card"><span>${label}</span><b>${value} <em>${unit}</em></b><small>${detail}</small></div>`;
  function render(){
    if(window.frameCAEUseStandaloneLocal?.())return;
    if(window.frameCAEUseAbaqusLocal?.()){window.frameCAERenderAbaqusReport?.();return;}
    const active=document.body.dataset.module==='local',confirmed=Boolean(window.frameCAEHasConfirmedModel?.());
    report.hidden=!active||!confirmed;cloudBar.hidden=charts.hidden=!active||!confirmed;
    if(!active||!confirmed)return;
    const r=localResult?.result,c=convergenceResult?.samples?convergenceResult:null,v=convergenceView(c);
    const currentLocal=Boolean(r&&!stale),currentConvergence=Boolean(c&&!stale&&convergenceSignature===convergenceRequestSignature());
    const state=busy?'正在计算':failure?'计算未完成':stale?'参数已修改':currentConvergence?v.passed?'固定热点已收敛':'固定热点未收敛':r?'已求解 · 待验证':'等待局部求解';
    report.innerHTML=`<div class="lr-head"><div><h2>局部分析结果</h2><p>当前节点 N${escape($('#genericNode').value)} · 应力单位 MPa</p></div><span class="lr-badge ${failure?'error':currentConvergence&&v.passed?'good':''}">${state}</span></div>`;
    let notice=busy?`${task}已运行 ${Math.floor((Date.now()-started)/1000)} 秒。细网格可能需要数分钟，请勿重复提交。`:failure?failure:stale?'节点或参数已修改，下方保留上次结果作参考。请重新计算后使用或导出。':r?r.concentrationResultNotice:'选择节点并识别参数，然后点击“计算局部应力”。';
    report.innerHTML+=`<div class="lr-notice ${failure?'error':''}" role="status">${escape(notice)}</div>`;
    if(r){report.innerHTML+=`<div class="lr-cards">${card('单元平均峰值 σVM',fmt(r.maximumVonMises/1e6,4),'MPa','全域单元平均最大值')}${card('节点平滑峰值 σVM',fmt(r.maximumNodalVonMises/1e6,4),'MPa','体积加权恢复值')}${card('名义应力 σnom',fmt(r.nominalStress/1e6,4),'MPa',`参考杆件 E${r.nominalStressReferenceElement??'—'}`)}${card('单元平均峰值 Kt',fmt(r.stressConcentrationFactor,4),'','诊断指标，需检查截断边界影响')}</div>`;
      if(finite(r.maximumIntegrationVonMises)){
        const xyz=value=>Array.isArray(value)?value.map(n=>fmt(n,5)).join(', '):'—';
        report.innerHTML+=`<div class="lr-cards">${card('积分点最大 σVM',fmt(r.maximumIntegrationVonMises/1e6,4),'MPa','已计算积分点中的最大值，非精确连续峰值')}</div><p class="lr-detail">位置（局部坐标 m，接头中心为原点）：<br>单元平均最大值所属单元中心：[${xyz(r.maximumLocationLocal)}]<br>平滑节点最大值位置：[${xyz(r.maximumNodalLocation)}]<br>积分点最大值位置：[${xyz(r.maximumIntegrationLocationLocal)}]</p><p class="lr-detail">${escape(r.loadTransferNotice)}<br>局部体力合力：[${xyz(r.localAppliedForce)}] N；切口反力合力：[${xyz(r.localReactionForce)}] N<br>合力平衡误差 ${fmt(r.forceBalanceError)} N；合力矩平衡误差 ${fmt(r.momentBalanceError)} N·m（平衡检查不等于网格收敛）。</p>`;
      }
      const checks=localResult.connection?.geometryChecks||{};
      report.innerHTML+=`<div class="lr-checks">${[['接头闭合',checks.junctionClosed],['实体单连通',checks.singleSolidComponent],['全 Hex8',checks.allHex8]].map(([name,ok])=>`<span class="${ok===true?'':'unknown'}">${ok===true?'✓':'?'} ${name}${ok===true?'通过':'未确认'}</span>`).join('')}</div><p class="lr-detail">${r.nodeCount.toLocaleString()} 节点 · ${r.elementCount.toLocaleString()} 单元 · ${r.freeDofCount.toLocaleString()} 自由度<br>局部 h = ${fmt(r.localMeshSize,4)} m · 平衡相对残差 ${fmt(r.relativeResidual,3)}（残差合格不等于应力收敛）</p>`;
      const max=(localResult.actualHexBoundary?.values||localResult.mesh.faceVonMises).reduce((m,n)=>finite(n)?Math.max(m,n):m,0);
      $('#localStressScale').innerHTML=`0 <i></i> ${fmt(max/1e6,4)} MPa · 真实网格边界面节点应力均值`;
    }else{$('#localStressScale').textContent='计算完成后显示带数值色标的真实网格云图。';}
    cloudBar.hidden=!r;$('#exportLocalFigure').disabled=busy||!currentLocal||Boolean(failure);
    charts.innerHTML=`<div class="lr-charthead"><div><h3>网格收敛验证</h3><p>固定表面位置 · 实际网格尺寸 · 后端判定</p></div><span class="lr-badge ${currentConvergence&&v.passed?'good':''}">${currentConvergence?v.passed?'通过 5% 判据':'尚未通过':c?'上次验证结果':'尚未验证'}</span></div>`;
    if(!v.samples.length){charts.innerHTML+=`<div class="lr-empty">${c?escape(c.stoppedReason):'展开左侧“3 网格收敛验证”后开始计算。'}<br>有云图表示完成一次求解，不能据此认定网格已收敛。</div>`;}
    else{charts.innerHTML+=chartSvg(c)+chartSvg(c,true)+`<p class="lr-detail">${escape(c.stoppedReason)}<br>${escape(c.notice)}</p><div class="lr-tablewrap"><table><thead><tr><th>档位</th><th>实际 h / m</th><th>${v.label}</th><th>节点峰值 Kt</th><th>变化</th></tr></thead><tbody>${v.samples.map((s,i)=>`<tr><td>${i+1}</td><td>${fmt(s.meshSize,4)}</td><td>${fmt(s[v.key],4)}</td><td>${fmt(s.smoothedStressConcentrationFactor,4)}</td><td>${i?fmt(v.changes[i-1]*100,3)+'%':'—'}</td></tr>`).join('')}</tbody></table></div>`;}
  }
  function setBusy(value){busy=value;for(const id of ['runGeneric','runGenericConvergence','autoGeneric','selectedGeneric'])$('#'+id).disabled=value;}
  async function run(kind){
    if(busy)return; if(!window.frameCAEHasConfirmedModel?.())return;
    task=kind==='local'?'局部实体求解':'网格收敛验证';failure='';started=Date.now();const pending=signature(),pendingConvergence=convergenceRequestSignature();setBusy(true);render();const timer=setInterval(render,1000);
    try{
      $('#error').style.display='none';$('#status').textContent=`正在执行${task}…`;
      const request={model:payload(),settings:genericLocalSettings()};
      if(kind==='convergence')Object.assign(request,{coarseSize:$('#genericCoarseSize').value,fineSize:$('#genericFineSize').value,sampleCount:$('#genericSampleCount').value,maxDofs:$('#genericMaxDofs').value});
      const response=await fetch(kind==='local'?'/api/local-generic-node':'/api/local-generic-convergence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
      const answer=await response.json();if(!response.ok)throw Error(answer.error||`${task}失败。`);
      if(signature()!==pending||(kind==='convergence'&&convergenceRequestSignature()!==pendingConvergence))throw Error('计算期间模型或参数已修改，本次结果未应用，请重新计算。');
      stale=false;
      if(kind==='local'){localResult=answer;convergenceResult=null;displayMode=document.body.dataset.module==='local'?'local':'global';localSignature=pending;convergenceSignature='';draw();writeGenericResults();$('#status').textContent='局部实体求解完成，网格收敛待验证。';}
      else{convergenceResult=answer;convergenceSignature=pendingConvergence;writeConvergenceResults();const v=convergenceView(answer);$('#genericConvergenceHint').textContent=answer.stoppedReason;$('#status').textContent=v.passed?'固定表面热点收敛验证通过。':'固定表面热点尚未收敛，请查看结果分析图。';}
    }catch(error){failure=error.message;$('#error').textContent=failure;$('#error').style.display='block';$('#status').textContent=`${task}失败，请查看错误提示。`;}
    finally{clearInterval(timer);setBusy(false);render();}
  }
  $('#runGeneric').onclick=()=>run('local');$('#runGenericConvergence').onclick=()=>run('convergence');
  const previousWrite=writeConvergenceResults;
  writeConvergenceResults=function(){if(convergenceResult?.convergenceMetric!=='trackedHotspotKt'){previousWrite();return;}const v=convergenceView(convergenceResult);$('#results').textContent+='\n\n固定表面热点收敛验证：\n'+v.samples.map((s,i)=>`档位 ${i+1}：h=${fmt(s.meshSize,5)} m；固定热点 Kt=${fmt(s[v.key],6)}`).join('\n')+`\n后端判定：${v.passed?'已通过':'未通过'}\n${convergenceResult.stoppedReason}\n${convergenceResult.notice}`;render();};
  const previousDraw=drawConvergence;drawConvergence=function(){if(document.body.dataset.module==='local'){render();return;}previousDraw();};
  const previousSettings=setGenericLocalSettings;setGenericLocalSettings=function(settings){previousSettings(settings);if(localSignature&&localSignature!==signature())stale=true;render();};
  $('#genericLocalSettings').addEventListener('input',event=>{if(event.target.id==='genericShowWeld')return;if(localSignature&&localSignature!==signature())stale=true;render();});
  $('#genericNode').addEventListener('change',()=>{if(localSignature&&localSignature!==signature())stale=true;render();});
  window.addEventListener('framecae-module-change',render);window.addEventListener('framecae:model-state',render);
  new MutationObserver(()=>{if(!busy)render();}).observe($('#status'),{childList:true,subtree:true,characterData:true});
  $('#exportLocalFigure').onclick=()=>{
    if(!localResult?.result||busy||stale)return;
    const r=localResult.result,c=convergenceResult?.samples&&convergenceSignature===convergenceRequestSignature()?convergenceResult:null,v=convergenceView(c),height=c?.samples.length?1190:770;
    const label=localSignature===signature()?'当前计算结果':'上次计算结果';
    const cloud=$('#scene').toDataURL('image/png');
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="${height}" viewBox="0 0 1000 ${height}"><rect width="1000" height="${height}" fill="white"/><g font-family="Segoe UI,Microsoft YaHei,sans-serif" fill="#354a6c"><text x="40" y="42" font-size="25">FrameCAE · 节点 N${escape($('#genericNode').value)} 局部分析</text><text x="40" y="72" font-size="14">${label} · ${escape(c?v.passed?'固定热点已收敛':'固定热点尚未收敛':'未进行网格收敛验证')}</text><text x="40" y="108" font-size="16">峰值 σVM = ${fmt(r.maximumVonMises/1e6,5)} MPa　名义应力 = ${fmt(r.nominalStress/1e6,5)} MPa　诊断 Kt = ${fmt(r.stressConcentrationFactor,5)}</text><image href="${cloud}" x="40" y="126" width="920" height="500" preserveAspectRatio="xMidYMid meet"/><text x="40" y="650" font-size="13">云图：真实网格边界面节点 von Mises 应力均值；峰值标记为节点平滑最大位置。</text><text x="40" y="678" font-size="13">${r.nodeCount} 节点 · ${r.elementCount} 单元 · ${r.freeDofCount} 自由度；平衡残差 ${fmt(r.relativeResidual)}</text><foreignObject x="40" y="694" width="920" height="75"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:13px;line-height:1.7;color:#7c602d">${escape(r.concentrationResultNotice)}</div></foreignObject>${c?.samples.length?`<svg x="40" y="780" width="920" height="230" viewBox="0 0 620 230">${chartSvg(c).replace(/^<svg[^>]*>|<\/svg>$/g,'')}</svg><foreignObject x="40" y="1040" width="920" height="130"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:13px;line-height:1.8;color:#596d88">${escape(c.stoppedReason)}<br/>${escape(c.notice)}</div></foreignObject>`:''}</g></svg>`;
    download(`FrameCAE_节点N${$('#genericNode').value}_局部分析.svg`,svg,'image/svg+xml;charset=utf-8');
  };
  render();
})();
