/* Confirmed hollow-tube textbook cases, reusing the normal project workflow. */
(() => {
  // Existing servers may still inject this script until restarted. The unified
  // archive panel owns textbook cases and legacy links, so do not add a second UI.
  if(document.querySelector('#archiveCasesPanel')||window.FrameCAEArchive)return;
  const $=s=>document.querySelector(s),anchor=$('#homeExample')||$('#homeStructure')?.closest('.start-card');if(!anchor)return;
  const box=document.createElement('section');box.id='textbookCasesPanel';box.style.cssText='border-top:1px solid #ddd;margin-top:15px;padding-top:12px';
  box.innerHTML='<h3>课本空间刚架 · 空心圆管</h3><select id="textbookCase"><option value="IV1">IV‑1 · 连续横梁与斜柱</option><option value="IV2">IV‑2 · 两跨空间刚架</option></select><p><button id="textbookGlobal" class="secondary">载入并计算 01</button> <button id="textbookLocal" class="secondary">打开 03 结果</button></p><select id="textbookRegion" aria-label="局部分析对象"></select><p id="textbookNotice" class="help">外径100mm、壁厚5mm；全固支。IV‑1计算N5为连续杆段，不生成焊接节点。</p>';
  anchor.after(box);let current=null;
  const progress=document.createElement('p');progress.id='textbookBatchProgress';progress.className='help';box.append(progress);
  async function refreshProgress(){
    try{const response=await fetch('/api/examples/textbook-progress'),answer=await response.json();if(!response.ok)return;
      const state={running:'正在计算全流程验证',completed:'全流程计算已结束，请分别查看各项是否通过',incomplete:'部分计算未完成，结果中保留具体原因',failed:'批量计算中断，已保留现有结果'}[answer.state]||'尚未开始批量计算';
      progress.textContent=state+'。'+answer.regions.map(x=>`${x.case} N${x.node} ${x.label}：${x.meshConverged===null?`${x.meshLevels}档有效网格`:x.meshConverged?'网格通过':'网格尚未通过'}，${x.cutConverged===null?'截取距离待检查':x.cutConverged?'截取距离通过':'截取距离尚未通过'}`).join('；');
    }catch(_){}
  }
  refreshProgress();setInterval(refreshProgress,6000);
  async function refresh(){const r=await fetch('/api/examples/textbook/'+$('#textbookCase').value);current=await r.json();if(!r.ok)throw Error(current.error);$('#textbookRegion').replaceChildren(...current.localTasks.map((t,i)=>new Option(t.label,String(i))));}
  async function open(local){
    $('#textbookGlobal').disabled=$('#textbookLocal').disabled=true;
    try{
      const region=Number($('#textbookRegion').value);await refresh();$('#textbookRegion').value=String(region);const task=current.localTasks[region]||current.localTasks[0];
      const expected=JSON.stringify(current.model.nodes);importModel(new File([JSON.stringify(current.model)],current.file,{type:'application/json'}));
      await new Promise((resolve,reject)=>{const start=Date.now();function check(){if(JSON.stringify(data.nodes)===expected&&Date.now()-start>200)resolve();else if(Date.now()-start>5000)reject(Error('模型未导入'));else setTimeout(check,50)}check()});
      $('#workspaceSidebar [data-module="global"]').click();await window.frameCAEConfirmModel();
      if(!window.frameCAEHasConfirmedModel())throw Error('01计算未完成');
      for(const id of ['strengthFy','strengthFt','strengthFc'])$('#'+id).value='235';
      $('#strengthHint').textContent='课本未给强度，235MPa为本次演示假设；应力需求可核对，工程强度结论须采用实际钢号。';
      window.frameCAEApplyStabilitySettings?.({defaultMuY:1,defaultMuZ:1,members:current.id==='IV1'?[{element:1,muY:2,muZ:2},{element:4,muY:2,muZ:2}]:[]});
      $('#stabilityHint').textContent='其他杆μ=1为演示假设。IV‑1原横梁长6m，人工分段点无侧向支承；两个3m计算段按μ=2保留6m有效长度。';
      FrameCAESolidPanel.applySettings(task.settings);
      if(local){$('#workspaceSidebar [data-module="local"]').click();FrameCAESolidPanel.applySettings(task.settings);$('#hubPreview').click();if(task.jobId){$('#hubSavedJob').value=task.jobId;$('#hubRestore').click();}}
      $('#textbookNotice').textContent=`${current.name}：01已重新计算。${local?(task.jobId?'正在读取本例对应的03结果；收敛状态见下方。':'03参数已填入，尚无完成作业。'):'可进入02、03、04、05查看。'}`;
    }catch(e){$('#textbookNotice').textContent=e.message;$('#status').textContent=e.message;}
    finally{$('#textbookGlobal').disabled=$('#textbookLocal').disabled=false;}
  }
  $('#textbookCase').onchange=()=>refresh().catch(e=>$('#textbookNotice').textContent=e.message);$('#textbookGlobal').onclick=()=>open(false);$('#textbookLocal').onclick=()=>open(true);
  refresh().catch(e=>$('#textbookNotice').textContent=e.message);window.FrameCAETextbookCases={open,refresh};
  const params=new URL(location.href).searchParams,requested=params.get('textbookCase');
  if(['IV1','IV2'].includes(requested))window.addEventListener('load',async()=>{
    try{
      await new Promise(resolve=>{let count=0;const ready=()=>{if(result?.nodes?.length||$('#status').textContent.includes('空白模型')||++count>100)resolve();else setTimeout(ready,100)};ready()});
      $('#textbookCase').value=requested;await refresh();const region=Number(params.get('region')||0);
      if(!Number.isInteger(region)||region<0||region>=current.localTasks.length)throw Error('局部对象编号无效');
      $('#textbookRegion').value=String(region);await open(true);
    }catch(e){$('#textbookNotice').textContent=e.message;}
  },{once:true});
})();
