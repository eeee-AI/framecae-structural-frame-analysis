/* All deliverable cases and direct saving into the archive's result folders. */
(() => {
  const install=()=>{
  const $=s=>document.querySelector(s),anchor=$('#homeExample')||$('#homeStructure')?.closest('.start-card')||$('#homeImport')?.closest('.start-card');if(!anchor)return false;
  const panel=document.createElement('section');panel.id='archiveCasesPanel';
  panel.style.cssText='border-top:1px solid #ddd;margin-top:16px;padding-top:12px';
  panel.innerHTML='<h3>算例与结果</h3><select id="archiveCase" aria-label="算例" style="max-width:100%;width:100%"></select><select id="archiveTask" aria-label="局部对象" style="max-width:100%;width:100%;margin-top:8px"></select><p style="display:flex;gap:8px;flex-wrap:wrap"><button id="archiveGlobal" class="secondary">载入并计算 01</button><button id="archiveLocal" class="secondary">打开本例 03</button><button id="archiveSave" class="secondary">保存当前网页结果</button></p><p id="archiveNotice" class="help">选择模型后载入；已完成03可直接恢复。新计算自动按算例保存。</p>';
  anchor.after(panel);let cases=[],checks={};
  if(['#archiveCasesPanel','#textbookCasesPanel'].includes(location.hash))setTimeout(()=>panel.scrollIntoView({block:'start'}),150);
  const note=s=>$('#archiveNotice').textContent=s;
  const key=()=>JSON.stringify(payload());
  const api=async(url,body)=>{const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const a=await r.json();if(!r.ok)throw Error(a.error||'请求失败');return a;};
  window.addEventListener('framecae:check-result',event=>{checks[event.detail.kind]={key:key(),answer:event.detail.answer};});
  async function refresh(){
    const a=await api('/api/archive/cases');cases=a.cases;const chosen=$('#archiveCase').value;
    const groups=[
      ['原有算例',c=>/^0[1-5]_/.test(c.id)],
      ['课本算例',c=>/^0[67]_/.test(c.id)],
      ['新增算例',c=>!/^0[1-7]_/.test(c.id)]
    ];
    $('#archiveCase').replaceChildren(...groups.map(([label,matches])=>{
      const group=document.createElement('optgroup');group.label=label;
      group.append(...cases.filter(matches).map(c=>new Option(c.name,c.id)));
      return group;
    }).filter(group=>group.children.length));
    if(cases.some(c=>c.id===chosen))$('#archiveCase').value=chosen;tasks();
  }
  function current(){return cases.find(c=>c.id===$('#archiveCase').value);}
  function tasks(){const c=current();$('#archiveTask').replaceChildren(...(c.tasks.length?c.tasks.map((t,i)=>new Option(t.label,String(i))):[new Option(`N${c.node} · 尚无03完成结果`,'0')]));}
  async function save(){if(!window.frameCAEHasConfirmedModel?.())throw Error('请先确认并计算01。');const valid={};for(const [kind,c] of Object.entries(checks))if(c.key===key())valid[kind]=c.answer;const a=await api('/api/archive/save',{model:payload(),globalResult:result,checks:valid});note('已保存到 '+a.folder+'。关闭计算后双击“更新项目压缩包.cmd”，将新结果写入同一个ZIP。');return a;}
  async function open(local){
    $('#archiveGlobal').disabled=$('#archiveLocal').disabled=true;
    try{
      const c=current(),task=c.tasks[Number($('#archiveTask').value)];checks={};window.FrameCAEArchiveJobId=null;
      importModel(new File([JSON.stringify(c.model)],c.id+'.json',{type:'application/json'}));
      const expected=JSON.stringify([c.model.nodes,c.model.elements]);
      await new Promise((resolve,reject)=>{const start=Date.now();function tick(){if(JSON.stringify([data.nodes,data.elements])===expected&&Date.now()-start>200)resolve();else if(Date.now()-start>6000)reject(Error('模型导入未完成'));else setTimeout(tick,50)}tick();});
      $('#workspaceSidebar [data-module="global"]').click();await window.frameCAEConfirmModel();
      if(!window.frameCAEHasConfirmedModel?.())throw Error($('#error').textContent||'01尚未完成');
      for(const id of ['strengthFy','strengthFt','strengthFc'])if($('#'+id))$('#'+id).value='235';
      $('#strengthHint').textContent='235MPa为归档演示假设；工程结论须采用实际钢号。';
      window.frameCAEApplyStabilitySettings?.({defaultMuY:1,defaultMuZ:1,members:c.id.startsWith('06_')?[{element:1,muY:2,muZ:2},{element:4,muY:2,muZ:2}]:[]});
      let settings=task?.settings;
      if(!settings){const q=await api('/api/solid-local/suggest',{model:payload(),globalSolution:{solvedModel:result.solvedModel,nodes:result.nodes},node:c.node,couplingMode:'forceSubmodel',shearDistribution:'saintVenantAnnulus'});settings={...q.geometry,...q.settingsSnapshot,node:q.node,couplingMode:q.couplingMode,shearDistribution:q.shearDistribution,cutLength:q.arms[0].length,meshSize:q.mesh.size,focusSize:q.mesh.focusSize,toeSize:q.mesh.toeSize,loadRadius:q.load.radius,loadDirection:q.load.direction};}
      FrameCAESolidPanel.applySettings(settings);
      window.FrameCAEArchiveJobId=task?.jobId||null;
      if(local){$('#workspaceSidebar [data-module="local"]').click();FrameCAESolidPanel.applySettings(settings);$('#hubPreview').click();if(task?.jobId){$('#hubSavedJob').value=task.jobId;$('#hubRestore').click();}}
      note(c.name+'：01已计算。'+(local?(task?.jobId?'正在恢复本例03结果，请分别查看求解和验证状态。':'03参数已填好；尚未求解。'): '可进入02、03、04、05操作。'));
    }catch(e){note(e.message);}finally{$('#archiveGlobal').disabled=$('#archiveLocal').disabled=false;}
  }
  $('#archiveCase').onchange=tasks;$('#archiveGlobal').onclick=()=>open(false);$('#archiveLocal').onclick=()=>open(true);$('#archiveSave').onclick=()=>save().catch(e=>note(e.message));
  const initialRefresh=refresh().catch(e=>note(e.message));window.FrameCAEArchive={refresh,open,save};
  const params=new URL(location.href).searchParams,legacy=params.get('textbookCase');
  if(['IV1','IV2'].includes(legacy))window.addEventListener('load',async()=>{
    try{
      await initialRefresh;
      const prefix=legacy==='IV1'?'06_':'07_',c=cases.find(item=>item.id.startsWith(prefix));
      if(!c)throw Error('未找到课本算例 '+legacy);
      const region=Number(params.get('region')||0);
      if(!Number.isInteger(region)||region<0||region>=c.tasks.length)throw Error('局部对象编号无效');
      await new Promise(resolve=>{let count=0;const ready=()=>{if(result?.nodes?.length||$('#status').textContent.includes('空白模型')||++count>100)resolve();else setTimeout(ready,100);};ready();});
      $('#archiveCase').value=c.id;tasks();$('#archiveTask').value=String(region);await open(true);
    }catch(e){note(e.message);}
  },{once:true});
  return true;
  };
  // workspace-ui builds the modern overview after this script is injected.
  // Retry once the page is fully built instead of silently omitting the panel.
  if(!install())window.addEventListener('load',install,{once:true});
})();
