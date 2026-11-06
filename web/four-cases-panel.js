/* Four complete frame models plus explicit local-joint configurations. */
(() => {
  const $=s=>document.querySelector(s),anchor=$('#homeExample');if(!anchor)return;
  const section=document.createElement('section');section.id='fourCasesPanel';
  section.style.cssText='margin-top:15px;padding-top:12px;border-top:1px solid #d9e4ef;max-width:100%';
  section.innerHTML='<label style="display:block;font-weight:600">四个空间刚架算例<select id="fourCaseSelect" style="display:block;max-width:100%;width:100%;margin:8px 0" aria-label="选择空间刚架算例"></select></label><div style="display:flex;gap:8px;flex-wrap:wrap"><button id="fourCaseGlobal" class="secondary">载入并计算 01</button><button id="fourCaseLocal" class="secondary">打开本例 03</button></div><p id="fourCaseNotice" class="help">一组固定截断参数与适中网格；03 使用外围梁与实体协调。</p>';
  anchor.after(section);let cases=[];
  const notice=text=>$('#fourCaseNotice').textContent=text;
  const entry=document.createElement('button');entry.className='secondary';entry.textContent='选择四个空间刚架算例';
  $('.file-menu-items').append(entry);entry.onclick=()=>{$('#workspaceSidebar [data-module="home"]').click();$('#fourCaseSelect').focus();};
  async function refreshCases(){
    const response=await fetch('/api/examples/four-models'),answer=await response.json();if(!response.ok)throw Error(answer.error||'算例无法读取。');
    cases=answer.cases;const current=$('#fourCaseSelect').value;
    $('#fourCaseSelect').replaceChildren(...cases.map(c=>new Option(`${c.number} · ${c.name}（03：N${c.settings.node}）`,String(c.number))));
    if(cases.some(c=>String(c.number)===current))$('#fourCaseSelect').value=current;
  }
  async function open(local){
    const number=Number($('#fourCaseSelect').value);for(const id of ['fourCaseGlobal','fourCaseLocal','fourCaseSelect'])$('#'+id).disabled=true;
    try{
      // Refresh finished-job availability; no job is submitted by this action.
      await refreshCases();$('#fourCaseSelect').value=String(number);
      const c=cases.find(c=>c.number===number);if(!c)throw Error('请先选择算例。');
      const modelSignature=m=>JSON.stringify([m.nodes,m.elements]);
      const expected=modelSignature(c.model);
      importModel(new File([JSON.stringify(c.model)],c.file,{type:'application/json'}));
      await new Promise((resolve,reject)=>{const start=Date.now();const check=()=>{
        if(modelSignature(data)===expected&&Date.now()-start>=180)resolve();
        else if(Date.now()-start>5000)reject(Error('导入未完成，请手动导入模型 JSON。'));else setTimeout(check,40);
      };check();});
      $('#workspaceSidebar [data-module="global"]').click();await window.frameCAEConfirmModel();
      if(!window.frameCAEHasConfirmedModel?.())throw Error($('#error').textContent||'整体模型未完成计算。');
      FrameCAESolidPanel.applySettings(c.settings);
      if(local){
        $('#workspaceSidebar [data-module="local"]').click();$('#hubPreview').click();
        if(c.jobId){$('#hubSavedJob').value=c.jobId;$('#hubRestore').click();notice(`已载入算例 ${number}，正在读取本次输入匹配的已完成结果。`);}
        else notice(`算例 ${number} 的 N${c.settings.node} 配置已填好；点击“用自编有限元计算应力”开始。`);
      }else notice(`算例 ${number} 已完成 01；可进入 05 查看位移内力，或返回此处打开本例 03。`);
    }catch(e){notice(e.message);$('#status').textContent=e.message;}
    finally{for(const id of ['fourCaseGlobal','fourCaseLocal','fourCaseSelect'])$('#'+id).disabled=false;}
  }
  $('#fourCaseGlobal').onclick=()=>open(false);$('#fourCaseLocal').onclick=()=>open(true);
  refreshCases().catch(e=>notice(e.message));
  window.FrameCAEFourCases={open,refresh:refreshCases};
})();
