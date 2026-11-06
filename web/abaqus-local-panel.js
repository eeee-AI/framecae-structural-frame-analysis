/* Module 03: external Abaqus jobs driven by the current 01 model. */
(() => {
  const $=s=>document.querySelector(s), panel=$('#genericLocalSettings');
  if(!panel)return;
  const mode=$('#genericConnectionType');
  mode.insertAdjacentHTML('afterbegin','<option value="integralHubRingButtWeld">B：一体节点件＋环形对接焊</option>');
  mode.value='integralHubRingButtWeld';
  const usesB=()=>mode.value==='integralHubRingButtWeld' && $('#genericSolverMethod').value==='abaqus';
  let geometryVersion=0;
  window.frameCAEUseAbaqusLocal=usesB;
  const section=document.createElement('section');section.id='abaqusHubSettings';
  section.innerHTML=`<h4>一体节点件与全熔透环焊缝</h4><div class="local-grid">
    <label>节点球半径 / m<input id="hubRadius" type="number" step=".001" value=".12"></label>
    <label>肩部圆角半径 / m<input id="hubBlend" type="number" step=".001" value=".015"></label>
    <label>截断距离 / m<input id="hubCut" type="number" step=".01" value=".8"></label>
    <label>环焊缝中心距离 / m<input id="hubWeldDistance" type="number" step=".001" value=".22"></label>
    <label>焊缝宽度 / m<input id="hubWeldWidth" type="number" step=".001" value=".018"></label>
    <label>焊缝外侧余高 / m<input id="hubReinforcement" type="number" step=".0005" value=".002"></label>
    <label>局部网格 / m<input id="hubFocus" type="number" step=".001" value=".008"></label>
    <label>焊趾网格 / m<input id="hubToeSize" type="number" step=".0005" value=".004"></label>
    <label>承载帽投影半径 / m<input id="hubLoadRadius" type="number" step=".001" value=".055"></label>
    <label>承载帽方向<select id="hubLoadDirection"><option value="0,0,1">全局 +Z</option><option value="0,0,-1">全局 −Z</option><option value="1,0,0">全局 +X</option><option value="-1,0,0">全局 −X</option><option value="0,1,0">全局 +Y</option><option value="0,-1,0">全局 −Y</option></select></label>
  </div><p class="help">支持 3–8 个任意方向的等径、等壁厚圆管杆端，中心及短颈一体。先识别选中节点，检查短颈空间，再计算。环焊缝按连续全熔透、与母材同一弹性材料处理；尺寸为可修改的演示假设。</p><p class="help">01 提供切口平移、转角及节点力/力矩。有节点外载时传递到承载区域，无外载时不设置加载耦合。肩部应力与环焊缝应力分别报告。</p><div id="hubArmSummary" class="help"></div><div class="actions"><button id="hubPreview" class="secondary">检查输入与受力</button><button id="hubDownloads" class="secondary" disabled>下载本次结果 JSON</button></div><label>已保存的作业编号<input id="hubSavedJob" type="text" maxlength="32" placeholder="输入已完成作业编号"></label><button id="hubRestore" class="secondary">读取匹配的已完成结果</button><div id="hubJobFiles" class="help"></div>`;
  $('#weldedConnectionSettings').append(section);
  const identityNote=document.createElement('p');identityNote.id='hubNodeIdentity';identityNote.className='help';
  $('#genericLocalHint').after(identityNote);
  const unify=document.createElement('button');unify.id='hubUnifySections';unify.className='secondary';unify.textContent='按圆管统一截面并重算 01';identityNote.after(unify);
  const caseLink=document.createElement('a');caseLink.href='/?verifiedCase=1';caseLink.target='_blank';caseLink.rel='noopener';caseLink.textContent='在新页面查看本机圆管验证算例';caseLink.className='help';caseLink.hidden=true;unify.after(caseLink);
  fetch('/api/abaqus-local/verified-case').then(r=>{caseLink.hidden=!r.ok;}).catch(()=>{});
  const solver=$('#genericSolverMethod');solver.insertAdjacentHTML('afterbegin','<option value="abaqus">Abaqus/Standard</option>');solver.value='abaqus';
  $('#genericMeshSize').value='.016';$('#genericToeRadius').value='.004';
  const baseSettings=genericLocalSettings;
  genericLocalSettings=()=>usesB()?{
    node:$('#genericNode').value,connectionType:mode.value,solverMethod:'abaqus',geometryVersion,
    hubRadius:$('#hubRadius').value,blendWidth:$('#hubBlend').value,cutLength:$('#hubCut').value,
    weldDistance:$('#hubWeldDistance').value,weldWidth:$('#hubWeldWidth').value,
    reinforcement:$('#hubReinforcement').value,toeRadius:$('#genericToeRadius').value,
    meshSize:$('#genericMeshSize').value,focusSize:$('#hubFocus').value,toeSize:$('#hubToeSize').value,
    loadRadius:$('#hubLoadRadius').value,loadDirection:$('#hubLoadDirection').value.split(',').map(Number),
  }:baseSettings();
  const signature=()=>JSON.stringify([payload(),genericLocalSettings(),...['genericCoarseSize','genericFineSize'].map(id=>$('#'+id).value)]);
  let busy=false,failure='',message='先完成 01，再检查所选节点。',currentJob='',accepted='',study=null;
  const fmt=(n,p=5)=>Number.isFinite(n)?Number(n).toPrecision(p):'—';
  const toeLabel=key=>key.replace('_inner',' 近节点侧焊趾').replace('_outer',' 远节点侧焊趾');
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function setLoadDirection(direction){
    const select=$('#hubLoadDirection'),value=direction.join(',');
    select.querySelectorAll('[data-automatic]').forEach(o=>o.remove());
    if(![...select.options].some(o=>o.value===value)){
      const option=new Option('自动选择的可用球面方向',value);option.dataset.automatic='true';select.add(option);
    }
    select.value=value;
  }
  function showArms(q){
    const audit=q.geometryPrecheck;
    const loaded=q.load.wrench.some(v=>Math.abs(v)>1e-12);
    $('#hubArmSummary').innerHTML=`<b>N${escape(q.node)} · ${q.arms.length} 个杆端</b> · ${loaded?'有直接节点外载':'无直接节点外载'}${audit?` · 最小夹角 ${fmt(audit.minimumAngleDegrees,4)}° · 短颈空间预检查通过`:''}<br>`+
      q.arms.map(a=>`E${a.element}：方向 (${a.direction.map(v=>fmt(v,3)).join(', ')})，截断 ${fmt(a.length,4)} m`).join('<br>');
    for(const id of ['hubLoadRadius','hubLoadDirection'])$('#'+id).disabled=!loaded;
  }
  const link=(id,name)=>`/api/abaqus-local/jobs/${id}/files/${name}`;
  const canonical=value=>typeof value==='number'&&Number.isFinite(value)?Number(value.toPrecision(13)):Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
  function cutDifference(c,offset){
    const expected=c.beamExpected.slice(offset,offset+3),actual=c.solidReaction.slice(offset,offset+3);
    const delta=Math.hypot(...actual.map((v,i)=>v-expected[i]));
    return Math.hypot(...expected)<1?`${fmt(delta,4)} ${offset?'N·m':'N'}（梁参考近零）`:
      `${fmt(100*delta/Math.hypot(...expected),4)}%`;
  }
  async function api(url,body){
    const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const answer=await response.json();if(!response.ok)throw Error(answer.error||'本机计算请求失败');return answer;
  }
  unify.onclick=async()=>{
    try{
      const previous=payload(),answer=await api('/api/abaqus-local/circular-sections',{model:previous,node:$('#genericNode').value});
      localStorage.setItem('framecaeBeforeCircularSections',JSON.stringify(previous));
      window.frameCAEUpdateSections(answer.model.sections);
      $('#builderConfirmModel').click();
      message='已按 D、A 更新所选节点相连圆管的 Iy/Iz/J，正在重算 01；旧输入已保存在本机页面备份。';failure='';render();
    }catch(e){failure=e.message;render();}
  };
  function setBusy(value){busy=value;for(const id of ['runGeneric','runGenericConvergence','autoGeneric','selectedGeneric','hubPreview','hubUnifySections'])$('#'+id).disabled=value;}
  function render(){
    if(!usesB())return;
    const identity=window.FrameCAEModelView.describeNode(payload(), $('#genericNode').value);
    identityNote.textContent=identity?`${identity.label} · 全局坐标 (${identity.coordinate.map(v=>Number(v.toPrecision(6))).join(', ')}) m；相连杆件：${identity.arms.map(a=>`E${a.element} → N${a.neighbor}`).join('；')}。局部原点为 ${identity.label}，XYZ 方向与 01 三维图一致。`:'';
    const active=document.body.dataset.module==='local'&&window.frameCAEHasConfirmedModel?.();
    const report=$('#localReport'),bar=$('#localCloudBar'),charts=$('#localCharts');
    if($('#visualDescription'))$('#visualDescription').textContent='真实 C3D10 网格云图 · 一体肩部与环焊缝分区应力';
    report.hidden=!active;bar.hidden=charts.hidden=!active;
    if(!active)return;
    const answer=localResult?.kind==='abaqusIntegralHub'?localResult:null,r=answer?.result;
    const evidence=answer?.verificationStudy;
    const allChecks=evidence&&evidence.sectionPassed&&evidence.geometryPassed&&evidence.meshPassed&&evidence.cutPassed&&evidence.samplingPassed&&evidence.forceBalancePassed;
    const state=busy?'正在计算':failure?'未完成':r?(evidence?(allChecks?'本次数值检查通过':'已求解 · 数值检查有未通过项'):'已求解 · 需验证'):'等待计算';
    report.innerHTML=`<div class="lr-head"><div><h2>一体节点件与环焊缝应力</h2><p>N${escape(answer?.node??$('#genericNode').value)} · Abaqus/Standard · C3D10</p></div><span class="lr-badge ${failure?'error':allChecks?'good':''}">${state}</span></div><div class="lr-notice" role="status">${escape(failure||message)}</div>`;
    bar.hidden=!r;$('#exportLocalFigure').disabled=busy||!r;
    if(r){
      const verification=answer.verificationStudy;
      report.innerHTML+=`<p class="lr-detail">截面一致性：${answer.sectionAudit?.passed?'已核对通过':'该作业未记录新截面核验'}；焊趾局部网格 ${fmt(r.toeMeshSize*1000,4)} mm。</p>`;
      if(verification){
        report.innerHTML+=`<div class="lr-notice">三档研究：焊趾峰值网格${verification.meshPeakPassed?'通过':'未通过'}，逐点应力分布${verification.meshProfilePassed?'通过':'未通过'}；截断距离：峰值${verification.cutPeakPassed?'通过':'未通过'}，逐点分布${verification.cutProfilePassed?'通过':'未通过'}。${escape(verification.conclusion)}</div>`;
        report.innerHTML+=`<p class="help">每道环焊缝分近节点侧、远节点侧两处焊趾，均位于管壁外表面。峰值检索全部焊趾边界单元节点，不跨单元平均。</p><div class="lr-tablewrap"><table><thead><tr><th>固定焊趾表面</th><th>本作业外推峰值 / MPa</th><th>研究状态</th></tr></thead><tbody>${Object.entries(verification.toes||{}).map(([k,v])=>`<tr><td>${escape(toeLabel(k))}</td><td>${fmt(v.peakMises/1e6)}</td><td>${v.meshPassed?'峰值网格通过':'峰值网格待改进'} / ${v.cutPassed?'峰值边界通过':'峰值边界敏感'}</td></tr>`).join('')}</tbody></table></div>`;
      }else report.innerHTML+='<p class="help">该作业尚未关联固定焊趾路径的网格和截断距离验证；不能仅凭求解完成认定焊趾已收敛。</p>';
      report.innerHTML+=`<div class="lr-cards"><div class="lr-card"><span>积分点最大 σVM</span><b>${fmt(r.maximumIntegrationPointVonMises/1e6)} <em>MPa</em></b><small>全域积分点最大值，含加载与切口附近</small></div><div class="lr-card"><span>一体肩部区域平均 σVM</span><b>${fmt(r.regions.SHOULDER?.volumeMeanElementMises/1e6)} <em>MPa</em></b><small>固定物理区域内的体积加权单元平均</small></div></div>`;
      report.innerHTML+=`<div class="lr-tablewrap"><table><thead><tr><th>区域</th><th>区域平均 / MPa</th><th>积分点最大 / MPa</th></tr></thead><tbody>${Object.entries(r.regions).filter(([name])=>name!=='BODY').map(([name,v])=>`<tr><td>${name==='SHOULDER'?'一体肩部':name==='PIPE'?'邻接管壁':escape(name.replace('WELD_E','环焊缝 E'))}</td><td>${fmt(v.volumeMeanElementMises/1e6)}</td><td>${fmt(v.maxIntegrationPointMises/1e6)}</td></tr>`).join('')}</tbody></table></div>`;
      const v=answer.validation;
      report.innerHTML+=`<p class="lr-detail">${r.nodeCount.toLocaleString()} 网格节点 · ${r.elementCount.toLocaleString()} C3D10 单元<br>总力平衡相对误差 ${fmt(v.forceBalanceRelativeError)}；总力矩平衡相对误差 ${fmt(v.momentBalanceRelativeError)}<br>切口位移最大误差 ${fmt(v.cutDisplacementMaxError)} m<br>区域平均用于比较，不等同于焊趾热点应力或疲劳强度。</p><details><summary>切口内力对照与建模假设</summary><p class="help">${answer.warnings.map(escape).join('<br>')}<br>网格分析检查：${escape(JSON.stringify(answer.meshQuality||{}))}</p><table><thead><tr><th>切口</th><th>合力差异</th><th>合矩差异</th></tr></thead><tbody>${v.cutComparisons.map(c=>`<tr><td>E${c.element}</td><td>${cutDifference(c,0)}</td><td>${cutDifference(c,3)}</td></tr>`).join('')}</tbody></table></details>`;
      const max=answer.mesh.faceVonMises.reduce((m,x)=>Math.max(m,x),0);
      $('#localStressScale').innerHTML=`0 <i></i> ${fmt(max/1e6)} MPa · 实体边界节点恢复应力`;
      report.innerHTML+='<p class="help">云图颜色采用平滑恢复应力；焊趾标记与表格采用未跨单元平均的外推峰值，两者数值口径不同。</p>';
    }
    charts.innerHTML='<h3>固定焊趾路径网格检查</h3><p class="help">每个杆端对应两侧焊趾表面。本轮采用一档网格、固定截断参数；应力结果尚未经网格收敛及截断距离敏感性验证。</p>';
    if(study){
      charts.innerHTML+=`<p>预设 5% 判据：焊趾峰值${study.peakPassed?'通过':'未通过'}，逐点分布${study.profilePassed?'通过':'未通过'}；截断距离须单独核对。</p><div class="lr-tablewrap"><table><thead><tr><th>焊趾网格 / mm</th><th>最大焊趾表面外推应力 / MPa</th><th>肩部平均 / MPa</th><th>全域积分点峰值 / MPa</th></tr></thead><tbody>${study.samples.map(s=>`<tr><td>${fmt(s.h*1000,3)}</td><td>${fmt(s.toePeak/1e6)}</td><td>${fmt(s.shoulder/1e6)}</td><td>${fmt(s.peak/1e6)}</td></tr>`).join('')}</tbody></table></div>`;
    }else charts.innerHTML+='<p class="help">本次界面尚未运行三档焊趾检查；已保存的验证范围见上方作业验证记录。</p>';
  }
  window.frameCAERenderAbaqusReport=render;
  window.frameCAERefreshAbaqusPanel=refreshMode;
  function refreshMode(){
    const b=usesB();section.hidden=!b;
    $('#genericWeldLeg').closest('label').hidden=b;$('#genericCutRatio').closest('label').hidden=b;
    solver.disabled=false;
    $('#weldedConnectionSettings .weld-badge').textContent=b?'一体节点件＋环形对接焊':'直接焊接圆管节点';
    const help=$('#genericWeldHint');help.hidden=b;
    $('#weldedConnectionSettings').querySelectorAll(':scope > p.help').forEach(p=>p.hidden=b);
    $('#runGeneric').textContent=b?'调用 Abaqus 计算应力':'计算局部应力';
    $('#runGenericConvergence').textContent=b?'运行三档 Abaqus 网格检查':'开始网格收敛验证';
    if(b){$('#genericCoarseSize').value='.004';$('#genericFineSize').value='.001';$('#genericSampleCount').value='3';}
    $('#genericSampleCount').disabled=b;$('#genericMaxDofs').closest('label').hidden=b;
    const legacyHelp=[...panel.querySelectorAll('p.help')].find(p=>p.textContent.startsWith('支持任意空间方向'));
    if(legacyHelp){legacyHelp.dataset.original||=legacyHelp.textContent;legacyHelp.textContent=b?'限非支座节点；杆端数量、截面和方向以所选求解器的输入检查为准。短颈相互重叠或截断空间不足会明确拒绝建模；截断面位于环焊缝外侧。':legacyHelp.dataset.original;}
    if(localResult){localResult=null;study=null;displayMode='global';draw();}render();
  }
  mode.addEventListener('change',refreshMode);
  async function identify(auto){
    try{
      if(!result)throw Error('请先在 01 完成当前整体模型求解。');
      const answer=await api('/api/abaqus-local/suggest',{model:payload(),...(auto?{}:{node:$('#genericNode').value})});
      geometryVersion=answer.schemaVersion>=2?2:0;
      $('#genericNode').value=String(answer.node);
      const fields={hubRadius:answer.geometry.hubRadius,hubBlend:answer.geometry.blendWidth,hubCut:answer.cutLength,
        hubWeldDistance:answer.geometry.weldDistance,hubWeldWidth:answer.geometry.weldWidth,
        hubReinforcement:answer.geometry.reinforcement,genericToeRadius:answer.geometry.toeRadius,
        genericMeshSize:answer.mesh.size,hubFocus:answer.mesh.focusSize,hubToeSize:answer.mesh.toeSize,hubLoadRadius:answer.load.radius};
      Object.entries(fields).forEach(([id,value])=>$('#'+id).value=value);
      setLoadDirection(answer.load.direction);
      showArms(answer);
      message=answer.message;$('#genericLocalHint').textContent=message;failure='';render();
    }catch(e){failure=e.message;render();}
  }
  const oldAuto=$('#autoGeneric').onclick,oldSelected=$('#selectedGeneric').onclick;
  $('#autoGeneric').onclick=()=>usesB()?identify(true):oldAuto?.();
  $('#selectedGeneric').onclick=()=>usesB()?identify(false):oldSelected?.();
  $('#hubPreview').onclick=async()=>{
    try{
      if(!result)throw Error('请先在 01 完成整体求解。');
      const q=await api('/api/abaqus-local/prepare',{model:payload(),settings:genericLocalSettings()});
      showArms(q);
      message=`N${q.node}：${q.arms.length} 处位移切口；节点力/力矩 [${q.load.wrench.join(', ')}]；${q.warnings.join(' ')}`;
      failure='';render();
    }catch(e){failure=e.message;render();}
  };
  function showFiles(id){
    $('#hubSavedJob').value=id;
    localStorage.setItem('framecaeAbaqusLastJob',id);
    const files=['local_request.json','model.inp','model.cae','model.odb','stress.csv','validation.json','toe_samples.json','abaqus.log'];
    if(localResult?.verificationStudy&&localResult.jobId===id)files.push('toe_validation.json');
    $('#hubJobFiles').innerHTML=`作业 ${escape(id)} · `+files.map(name=>`<a href="${link(id,name)}" target="_blank">${name}</a>`).join(' · ');
  }
  $('#hubSavedJob').value=localStorage.getItem('framecaeAbaqusLastJob')||'';
  $('#hubRestore').onclick=async()=>{
    if(busy)return;
    const pending=signature(),id=$('#hubSavedJob').value.trim();setBusy(true);failure='';
    try{
      if(!result||!window.frameCAEHasConfirmedModel?.())throw Error('请先确认并计算 01 当前模型。');
      const saved=await api(link(id,'local_request.json'));
      const current=await api('/api/abaqus-local/prepare',{model:payload(),settings:genericLocalSettings()});
      // Compare the complete local physical problem, independent of cosmetic
      // fields added by the editable 01 form to the raw model JSON.
      if(!window.FrameCAEModelView.localProblemMatches(saved,current))throw Error('该作业与当前模型、几何、载荷或网格不匹配；请恢复原输入或重新计算。');
      const answer=await api(`/api/abaqus-local/jobs/${id}/result`);
      if(signature()!==pending)throw Error('读取期间输入已改变，未应用旧结果。');
      currentJob=id;localResult=answer;localResult.jobId=id;convergenceResult=null;study=null;accepted=pending;
      showFiles(id);displayMode='local';draw();$('#hubDownloads').disabled=false;
      message='已读取输入匹配的已完成作业。验证状态以该作业记录为准。';
      $('#results').textContent=JSON.stringify({jobId:id,result:answer.result,validation:answer.validation},null,2);
    }catch(e){failure=e.message;}
    finally{setBusy(false);render();}
  };
  async function submit(request,pending,label){
    const job=await api('/api/abaqus-local/jobs',request);currentJob=job.jobId;showFiles(currentJob);
    while(true){
      const state=await api(`/api/abaqus-local/jobs/${job.jobId}`);
      message=`${label}${state.message}`;render();$('#status').textContent=message;
      if(state.state==='failed')throw Error(state.message);
      if(state.state==='completed'){
        const answer=await api(`/api/abaqus-local/jobs/${job.jobId}/result`);
        if(signature()!==pending)throw Error('计算期间模型或参数已改变，已保存作业，但未应用到当前模型。');
        return {answer,jobId:job.jobId};
      }
      await new Promise(resolve=>setTimeout(resolve,1800));
    }
  }
  const oldRun=$('#runGeneric').onclick,oldConvergence=$('#runGenericConvergence').onclick;
  async function run(convergence){
    if(busy)return;
    const pending=signature();setBusy(true);failure='';study=null;localResult=null;displayMode='global';draw();render();
    try{
      if(!result)throw Error('请先完成 01 整体求解。');
      const settings=genericLocalSettings(),model=payload();
      const coarse=Number($('#genericCoarseSize').value),fine=Number($('#genericFineSize').value);
      if(convergence&&!(coarse>fine&&fine>0))throw Error('三档网格检查要求粗网格大于细网格且均为正数。');
      const sizes=convergence?[coarse,Math.sqrt(coarse*fine),fine]:[Number(settings.toeSize)],samples=[];
      let last;
      for(let i=0;i<sizes.length;i++){
        last=await submit({model,settings:{...settings,toeSize:sizes[i]}},pending,convergence?`第 ${i+1}/3 档：`:'');
        const r=last.answer.result;
        const toeSamples=convergence?await api(link(last.jobId,'toe_samples.json')):null;
        samples.push({jobId:last.jobId,h:r.toeMeshSize,requestedSize:sizes[i],toeSamples,
          toePeak:Math.max(...Object.values(last.answer.toePaths||{}).map(v=>v.peakMises),0),shoulder:r.regions.SHOULDER.volumeMeanElementMises,
          weld:Math.max(...Object.entries(r.regions).filter(([k])=>k.startsWith('WELD')).map(([,v])=>v.volumeMeanElementMises)),
          peak:r.maximumIntegrationPointVonMises,regions:r.regions});
      }
      localResult=last.answer;localResult.jobId=last.jobId;accepted=pending;convergenceResult=null;
      if(convergence){
        const names=Object.keys(samples[0].toeSamples.records);
        const peakPassed=samples.slice(1).every((s,i)=>names.every(k=>
          Math.abs(s.toeSamples.records[k].peakMises-samples[i].toeSamples.records[k].peakMises)/Math.max(s.toeSamples.records[k].peakMises,1)<=.05));
        const profilePassed=samples.slice(1).every((s,i)=>names.every(k=>{
          const current=s.toeSamples.samples[k],previous=samples[i].toeSamples.samples[k],peak=Math.max(s.toeSamples.records[k].peakMises,1);
          return s.toeSamples.records[k].resolutionPassed&&samples[i].toeSamples.records[k].resolutionPassed&&
            current.every((value,j)=>Math.abs(value-previous[j])/peak<=.05);
        }));
        study={samples,passed:peakPassed&&profilePassed,peakPassed,profilePassed};localResult.meshStudy=study;
      }
      displayMode=document.body.dataset.module==='local'?'local':'global';draw();
      message=convergence?'三档焊趾计算已完成，请查看峰值与固定路径收敛状态。':'已完成本次求解；网格和截断距离验证以本次作业关联记录为准。';
      $('#hubDownloads').disabled=false;
      $('#results').textContent=JSON.stringify({jobId:currentJob,result:localResult.result,validation:localResult.validation,warnings:localResult.warnings},null,2);
    }catch(e){failure=e.message;$('#error').textContent=failure;$('#error').style.display='block';localResult=null;}
    finally{setBusy(false);render();$('#status').textContent=failure?'Abaqus 计算未完成，请查看原因与作业日志。':message;}
  }
  $('#runGeneric').onclick=()=>usesB()?run(false):oldRun?.();
  $('#runGenericConvergence').onclick=()=>usesB()?run(true):oldConvergence?.();
  $('#hubDownloads').onclick=()=>{
    if(localResult?.kind==='abaqusIntegralHub'&&accepted===signature())download(`FrameCAE_N${localResult.node}_Abaqus结果.json`,JSON.stringify(localResult,null,2),'application/json');
  };
  const oldExport=$('#exportLocalFigure').onclick;
  $('#exportLocalFigure').onclick=()=>{
    if(!usesB())return oldExport?.();
    if(!localResult||accepted!==signature())return;
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900"><rect width="1200" height="900" fill="white"/><text x="30" y="35" font-size="22">FrameCAE N${localResult.node} · Abaqus C3D10</text><image href="${$('#scene').toDataURL('image/png')}" x="20" y="60" width="1160" height="760"/><text x="30" y="860" font-size="16">真实网格边界恢复应力；网格与截断距离验证状态请参阅本次 JSON。</text></svg>`;
    download(`FrameCAE_N${localResult.node}_Abaqus云图.svg`,svg,'image/svg+xml');
  };
  setInterval(()=>{
    if(!usesB()||!accepted||accepted===signature())return;
    accepted='';study=null;
    if(localResult?.kind==='abaqusIntegralHub'){localResult=null;displayMode='global';draw();}
    $('#hubDownloads').disabled=true;message='模型、节点或参数已修改，上次结果已失效，请重新计算。';render();
  },700);
  window.addEventListener('framecae-module-change',render);window.addEventListener('framecae:model-state',render);
  $('#genericNode').addEventListener('change',()=>{render();});
  refreshMode();
  // An explicit result URL opens an independent verified circular example.
  // Ordinary project URLs never replace the currently edited model.
  if(new URL(location.href).searchParams.get('verifiedCase')==='1'){
    window.addEventListener('load',async()=>{
      try{
        const reference=await api('/api/abaqus-local/verified-case');
        await new Promise(resolve=>{const ready=()=>{if(typeof data==='object'&&data.nodes?.length&&result?.elements?.length)resolve();else setTimeout(ready,100);};ready();});
        $('#workspaceSidebar [data-module="global"]').click();
        data=JSON.parse(JSON.stringify(reference.model));renderTables();
        await window.frameCAEConfirmModel();
        $('#workspaceSidebar [data-module="local"]').click();
        const ids={node:'genericNode',meshSize:'genericMeshSize',focusSize:'hubFocus',toeSize:'hubToeSize',cutLength:'hubCut'};
        Object.entries(ids).forEach(([key,id])=>{if(reference.settings[key]!==undefined)$('#'+id).value=reference.settings[key];});
        $('#hubSavedJob').value=reference.jobId;$('#hubRestore').click();
      }catch(e){failure=e.message;render();}
    },{once:true});
  }
})();
