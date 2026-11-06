/* B self-coded solver integrated into the existing 03 controls, not a separate app. */
(() => {
  // One additional refinement, compared with the unchanged baseline. This is
  // a two-level mesh check, not a claim of full mesh/cut-length convergence.
  function singleRefinementSizes(value){
    const coarse=Number(value),fine=Number((coarse/Math.sqrt(2)).toPrecision(10));
    if(!Number.isFinite(coarse)||coarse>.004||fine<.0005)throw Error('加密检查要求当前关注区网格大于等于0.708 mm且不超过4 mm；更细网格请使用专项网格研究。');
    return [coarse,fine];
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={singleRefinementSizes};
  if(typeof document==='undefined')return;
  const $=s=>document.querySelector(s),selector=$('#genericSolverMethod'),mode=$('#genericConnectionType');if(!selector)return;
  selector.insertAdjacentHTML('afterbegin','<option value="standalone">自编有限元 · 曲边 Tet10</option>');selector.value='standalone';
  const isB=()=>mode.value==='integralHubRingButtWeld',active=()=>isB()&&selector.value==='standalone';
  window.frameCAEUseStandaloneLocal=active;
  const previousSettings=genericLocalSettings;
  genericLocalSettings=()=>active()?{node:Number($('#genericNode').value),analysisType:$('#solidAnalysisType').value,patchWidth:Number($('#solidPatchWidth').value),patchAngleDegrees:Number($('#solidPatchAngle').value),connectionType:mode.value,solverMethod:'standalone',couplingMode:$('#solidCouplingMode').value,shearDistribution:$('#solidShearDistribution').value,hubRadius:Number($('#hubRadius').value),blendWidth:Number($('#hubBlend').value),cutLength:Number($('#hubCut').value),weldDistance:Number($('#hubWeldDistance').value),weldWidth:Number($('#hubWeldWidth').value),reinforcement:Number($('#hubReinforcement').value),toeRadius:Number($('#genericToeRadius').value),meshSize:Number($('#genericMeshSize').value),focusSize:Number($('#hubFocus').value),toeSize:Number($('#hubToeSize').value),loadRadius:Number($('#hubLoadRadius').value),loadDirection:$('#hubLoadDirection').value.split(',').map(Number)}:previousSettings();
  const globalSolution=()=>{if(!window.frameCAEHasConfirmedModel?.()||!result?.solvedModel)throw Error('请先确认并计算当前模型的01。');return {solvedModel:result.solvedModel,nodes:result.nodes};};
  const requestBody=()=>({model:payload(),settings:genericLocalSettings(),globalSolution:globalSolution(),archiveJobId:window.FrameCAEArchiveJobId||null});
  let identifiedModel='';
  const signature=()=>JSON.stringify([payload(),genericLocalSettings(),$('#genericCoarseSize').value,$('#genericFineSize').value]);
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=(v,d=4)=>Number.isFinite(v)?Number(v).toPrecision(d):'—';
  let busy=false,job='',accepted='',note='先完成 01，再计算所选 B 节点。',failure='',pendingCancel=false;
  const cancel=document.createElement('button');cancel.id='solidCancel';cancel.className='secondary';cancel.textContent='取消计算';cancel.hidden=true;$('#runGeneric').after(cancel);
  const couplingControl=document.createElement('label');couplingControl.className='help';couplingControl.innerHTML='子模型边界方式 <select id="solidCouplingMode"><option value="forceSubmodel">截面内力驱动：适用于荷载控制</option></select>';$('#hubPreview').parentElement.before(couplingControl);
  const shearControl=document.createElement('label');shearControl.className='help';shearControl.innerHTML='切口剪力分布 <select id="solidShearDistribution"><option value="saintVenantAnnulus">圣维南圆环截面解</option><option value="resultantAffine">原等效分布（对照）</option></select>';couplingControl.after(shearControl);
  $('#solidCouplingMode').value='forceSubmodel';
  const analysisControl=document.createElement('div');analysisControl.className='help';analysisControl.innerHTML='局部对象 <select id="solidAnalysisType"><option value="auto">自动识别真实接头、连续杆段、理想固支</option><option value="continuousPipe">连续直圆管（计算分段点，无焊缝）</option><option value="idealClamp">单根圆管理想固支端</option></select> 加载面片宽度 / m <input id="solidPatchWidth" type="number" value="0.02" step="0.005" style="width:80px"> 周向角 / ° <input id="solidPatchAngle" type="number" value="60" style="width:65px">';shearControl.after(analysisControl);
  function applySettings(settings){
    const ids={node:'genericNode',hubRadius:'hubRadius',blendWidth:'hubBlend',cutLength:'hubCut',weldDistance:'hubWeldDistance',weldWidth:'hubWeldWidth',reinforcement:'hubReinforcement',toeRadius:'genericToeRadius',meshSize:'genericMeshSize',focusSize:'hubFocus',toeSize:'hubToeSize',loadRadius:'hubLoadRadius',couplingMode:'solidCouplingMode',shearDistribution:'solidShearDistribution'};
    for(const [key,id] of Object.entries(ids))if(settings[key]!==undefined)$('#'+id).value=settings[key];
    $('#solidAnalysisType').value=settings.analysisType||'auto';
    if(settings.patchWidth!==undefined)$('#solidPatchWidth').value=settings.patchWidth;
    if(settings.patchAngleDegrees!==undefined)$('#solidPatchAngle').value=settings.patchAngleDegrees;
    if(settings.loadDirection){const value=settings.loadDirection.join(','),select=$('#hubLoadDirection');if(![...select.options].some(o=>o.value===value))select.add(new Option('自动选择的可用球面方向',value));select.value=value;}
    if(localResult?.kind==='standaloneIntegralHub'){localResult=null;accepted='';displayMode='global';}
    $('#hubArmSummary').textContent='参数已更新；点击“检查输入与受力”核对本次杆件和截断面。';
    selector.value='standalone';mode.value='integralHubRingButtWeld';failure='';refresh();
    identifiedModel=JSON.stringify(payload());
  }
  const fresh=document.createElement('label');fresh.id='solidFreshControl';fresh.className='help';fresh.innerHTML='<input id="solidForceRerun" type="checkbox"> 重新求解（不复用历史结果）';cancel.after(fresh);
  const taskControl=document.createElement('div');taskControl.className='help';taskControl.innerHTML='<button id="solidImportTask" class="secondary">导入03参数与结果</button> <button id="solidExportTask" class="secondary">导出03参数</button><input id="solidTaskFile" type="file" accept=".json" hidden><small> 适用于任意当前模型；只载入参数，不替换01模型。</small>';fresh.after(taskControl);
  const old={};for(const id of ['runGeneric','runGenericConvergence','hubPreview','hubRestore','hubDownloads','exportLocalFigure','autoGeneric','selectedGeneric'])old[id]=$('#'+id).onclick;
  const exports=['member_load_transfer.json','source_01.json','local_request.json','local_results.json','validation.json','mesh_meta.json','toe_results.json','shoulder_results.json','worker.log','mesh.msh','geometry.step','model.inp','result.vtu','solution.npz','stress.csv','study.json','joint_mesh_study.json','submodel.json','member_load_transfer.json'];
  async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const a=await r.json();if(!r.ok)throw Error(a.error||'独立求解请求失败');return a;}
  const path=(id,suffix='')=>'/api/solid-local/jobs/'+id+suffix;
  function setBusy(value){busy=value;for(const id of ['runGeneric','runGenericConvergence','hubPreview','hubRestore','autoGeneric','selectedGeneric','solidCouplingMode','solidShearDistribution','solidImportTask','solidExportTask'])$('#'+id).disabled=value;cancel.hidden=!value;cancel.disabled=false;}
  function links(files){$('#hubJobFiles').innerHTML=files.filter(n=>exports.includes(n)).map(n=>`<a download="${n}" href="${path(job,'/files/'+n)}">${escape(n)}</a>`).join(' · ');}
  function render(){
    if(!active())return;
    const r=localResult?.kind==='standaloneIntegralHub'?localResult:null,identity=FrameCAEModelView.describeNode(payload(),$('#genericNode').value);
    $('#hubNodeIdentity').textContent=identity?`${identity.label} · 全局坐标 (${identity.coordinate.join(', ')}) m；${identity.arms.map(a=>`E${a.element} → N${a.neighbor}`).join('；')}。XYZ 与 01 一致。`:'';
    const show=document.body.dataset.module==='local'&&window.frameCAEHasConfirmedModel?.();$('#localReport').hidden=!show;$('#localCharts').hidden=!show;$('#localCloudBar').hidden=!show||!r;if(!show)return;
    const status=busy?'正在计算':failure?'未完成':r?'已求解 · 验证状态分列':'等待计算';
    $('#localReport').innerHTML=`<div class="lr-head"><div><h2>B 节点与环焊缝应力</h2><p>N${escape(r?.node??$('#genericNode').value)} · 自编曲边 Tet10 · 无需 Abaqus</p></div><span class="lr-badge ${failure?'error':''}">${status}</span></div><div class="lr-notice" role="status">${escape(failure||note)}</div>`;
    $('#hubDownloads').disabled=!r||busy;$('#exportLocalFigure').disabled=!r||busy;
    if(!r){$('#localCharts').innerHTML='<p class="help">计算后显示本次网格、平衡检查和切口传力比较；历史验证不会自动套用到新输入。</p>';return;}
    if(r.analysisType){renderLine(r);return;}
    const v=r.validation,s=r.result,peaks=Object.entries(r.toePaths||{}),maxToe=Math.max(...peaks.map(([,p])=>p.nodePeakMisesPa));
    $('#hubArmSummary').textContent=r.tubeArms.map(a=>`E${a.element}：方向 (${a.direction.map(x=>fmt(x)).join(', ')})；切口 ${fmt(a.length)} m`).join('；');
    $('#visualDescription').textContent='曲边 Tet10 实际表面 · 拖动旋转 · 全局 XYZ / m';
    $('#legendText').textContent='节点平均 Mises 云图；焊趾表格采用未平均单侧应力';
    $('#localReport').innerHTML+=`<div class="lr-cards"><div class="lr-card"><span>焊趾未平均最大值</span><b>${fmt(maxToe/1e6)} <em>MPa</em></b><small>每根管件两处环焊趾，单元侧应力</small></div><div class="lr-card"><span>全模型未平均最大值</span><b>${fmt(s.maximumElementNodalMisesPa/1e6)} <em>MPa</em></b><small>可能来自肩部、加载区或切口</small></div></div><p>${s.nodeCount.toLocaleString()} 网格节点 · ${s.elementCount.toLocaleString()} 曲边 Tet10 · 切口 ${fmt(s.cutLength)} m · 焊趾网格 ${fmt(s.toeMeshSize*1000)} mm</p><p>数值平衡/残差：${v.numericalPassed?'通过':'未通过'}；01位移/转角传递：${v.boundaryTransferPassed?'通过':'未通过'}；切口受力参考对照：${v.globalLocalTransmission==='passed'?'差异在5%内':'存在差异，需评估局部刚度影响'}；截断距离：未比较；强度：未判定。</p><p class="help">相对残差 ${fmt(v.relativeResidual)}；合力误差 ${fmt(v.forceBalanceRelativeError)}；合矩误差 ${fmt(v.momentBalanceRelativeError)}；切口位移误差 ${fmt(v.cutDisplacementMaxError)} m。</p><div class="lr-tablewrap"><table><thead><tr><th>焊趾位置</th><th>未平均峰值 / MPa</th></tr></thead><tbody>${peaks.map(([name,p])=>`<tr><td>${escape(name.replace('_near',' 近节点侧').replace('_far',' 远节点侧'))}</td><td>${fmt(p.nodePeakMisesPa/1e6)}</td></tr>`).join('')}</tbody></table></div><details><summary>切口反力与01梁截面内力对照（反力为求解输出）</summary><p>全局 XYZ；各力矩均关于对应切口中心；力为作用于保留节点区域的方向。03只施加01的截面运动，表内反力不另行加载。理想梁节点与实际节点件刚度不同，两者受力可以不同；明显差异须进一步评估精度。</p><div class="lr-tablewrap"><table><thead><tr><th>切口</th><th>${r.coupling?'协调梁':'01'} 的 F / N</th><th>实体 F / N</th><th>${r.coupling?'协调梁':'01'} 的 M / N·m</th><th>实体 M / N·m</th></tr></thead><tbody>${v.cutResultants.map(c=>`<tr><td>E${c.element}</td><td>${c.beamExpected.slice(0,3).map(x=>fmt(x)).join(', ')}</td><td>${c.solidReaction.slice(0,3).map(x=>fmt(x)).join(', ')}</td><td>${c.beamExpected.slice(3).map(x=>fmt(x)).join(', ')}</td><td>${c.solidReaction.slice(3).map(x=>fmt(x)).join(', ')}</td></tr>`).join('')}</tbody></table></div></details><details><summary>本次模型假设与适用范围</summary><p>${r.warnings.map(escape).join('<br>')}</p></details>`;
    if(r.submodel){
      const force=true,method='01截面内力驱动子模型';
      const report=$('#localReport');
      report.innerHTML=report.innerHTML.replace('01位移/转角传递：','01合力/合矩传递：').replace('切口位移误差 ','边界传递误差 ')
        .replace('03只施加01的截面运动，表内反力不另行加载。','本模式施加01的切口合力和合矩，切口位移是求解输出。守恒不是独立精度验证。');
      if(force){
        report.innerHTML+=`<p>切口剪力分布：${r.submodel.shearDistribution==='saintVenantAnnulus'?'圣维南圆环截面解；保留原轴力、弯矩和扭矩分布':'原等效分布（对照）'}。守恒与虚功检查不代表峰值应力精度已验证。</p>`;
        if(r.submodel.shearDistribution==='saintVenantAnnulus'){
          const audits=r.submodel.cuts.map(c=>c.shearTransfer),passed=audits.every(a=>a&&Number.isFinite(a.virtualWorkRelativeError)&&a.virtualWorkRelativeError<=1e-10&&a.maximumCorrectionRelative<=.01);
          report.innerHTML+=`<p>圣维南载荷传递检查：${passed?'通过':'未通过'}；表面载荷与等效节点力的虚功相对差最大值 ${fmt(Math.max(...audits.map(a=>a?.virtualWorkRelativeError??Infinity)))}；曲面/积分修正最大相对量 ${fmt(Math.max(...audits.map(a=>a?.maximumCorrectionRelative??Infinity)))}。六分量守恒另见切口载荷核对。</p>`;
        }
        const error=offset=>Math.max(...v.cutResultants.map(c=>Math.hypot(...c.solidReaction.slice(offset,offset+3).map((x,k)=>x-c.beamExpected[offset+k]))));
        report.innerHTML=report.innerHTML.replace('切口反力与01梁截面内力对照（反力为求解输出）','切口载荷与01截面内力核对（边界构造检查）')
          .replace(`边界传递误差 ${fmt(v.cutDisplacementMaxError)} m。`,`合力传递误差 ${fmt(error(0))} N；合矩传递误差 ${fmt(error(3))} N·m。`)
          .replace('切口受力参考对照：差异在5%内','截面载荷守恒：通过（边界构造检查）');
      }
      report.innerHTML+=`<p class="lr-notice"><b>${method}</b>：01位移只确定刚体姿态，切口变形由03实体刚度求得。整体结果不会被03改写。网格与截断距离需另行核验。</p>`;
    }
    if(r.memberLoadTransfer){
      const t=r.memberLoadTransfer;
      $('#localReport').innerHTML+=`<p><b>保留区均布载荷传递：${t.passed?'通过':'未通过'}</b>；${escape(t.assumption)}</p><details><summary>各杆q、加载区间与守恒/虚功检查</summary><table><tr><th>杆件</th><th>全局q / N/m（含自重）</th><th>原杆受载区间 / m</th><th>合力相对误差</th><th>合矩相对误差</th><th>梁虚功相对误差</th><th>离散虚功相对误差</th></tr>${t.arms.map(a=>`<tr><td>E${a.element}</td><td>${a.globalQ.map(x=>fmt(x)).join(', ')}</td><td>${a.originalMemberIntervalM.map(x=>fmt(x)).join('～')}</td><td>${fmt(a.forceRelativeError)}</td><td>${fmt(a.momentRelativeError)}</td><td>${fmt(a.beamVirtualWorkRelativeError)}</td><td>${fmt(a.discreteVirtualWorkRelativeError)}</td></tr>`).join('')}</table><p>管壁、节点件及交汇区域按最近归一化杆轴唯一划分；各杆的线荷载分别积分后叠加。自重采用01理想梁线质量，不另加节点件体积重量。</p></details>`;
    }
    const study=r.verificationStudy;
    $('#localCharts').innerHTML=study?`<h3>本次固定焊趾路径网格检查</h3><p>峰值：${study.lastPair.peakPassed?'通过':'未通过'}；分布 RMS：${study.lastPair.profileRmsPassed?'通过':'未通过'}；逐点最大差异：${study.lastPair.profileMaxPassed?'通过':'未通过'}。${escape(study.scope)}</p><div class="lr-tablewrap"><table><tr><th>焊趾网格 / mm</th><th>焊趾峰值 / MPa</th></tr>${study.cases.map(c=>`<tr><td>${fmt(c.toeSizeM*1000)}</td><td>${fmt(Math.max(...Object.values(c.toes).map(t=>t.nodePeakMisesPa))/1e6)}</td></tr>`).join('')}</table></div>`:'<h3>验证范围</h3><p>本次为单档网格，网格收敛未比较。可运行多档焊趾网格检查；它不代表肩部网格、截断距离或实际接头强度均已验证。</p>';
    const joint=r.jointMeshVerification;
    if(joint&&joint.jobId===r.jobId&&joint.fingerprint===r.fingerprint){
      const pair=joint.lastPair,percent=x=>fmt(x*100,3)+'%';
      $('#localCharts').innerHTML=`<h3>本结果的焊趾与肩部网格研究</h3><p>网格判据：${joint.converged?'通过':'尚未通过'}；共${joint.levels.length}档，几何、01源解及截断距离保持不变。</p><div class="lr-tablewrap"><table><tr><th>焊趾尺寸 / mm</th><th>节点数</th><th>焊趾峰值 / MPa</th><th>肩部峰值 / MPa</th></tr>${joint.levels.map(c=>`<tr><td>${fmt(c.toeSizeM*1000)}</td><td>${Number(c.nodes).toLocaleString()}</td><td>${fmt(c.toeMPa)}</td><td>${fmt(c.shoulderMPa)}</td></tr>`).join('')}</table></div>${pair?`<p>末两档峰值变化：焊趾 ${percent(pair.toe.peakRelativeChange)}，肩部 ${percent(pair.shoulder.peakRelativeChange)}；固定位置应力最大变化：焊趾 ${percent(pair.toe.profileMaxRelativeChange)}，肩部 ${percent(pair.shoulder.profileMaxRelativeChange)}。</p>`:''}<p class="help">${escape(joint.criterion)} 实际接头强度尚未判定；此记录只适用于本次作业。</p>`;
    }
    appendCutStudy(r);
    window.frameCAERefreshVisualWorkbench?.();
    $('#visualDescription').textContent='曲边 Tet10 实际表面 · 拖动旋转 · 全局 XYZ / m';
  }
  function appendCutStudy(r){
    const flux=r.validation?.stressFluxComparison;
    if(flux)$('#localReport').innerHTML+=`<p><b>由应力 σ·n 独立积分的切口核对：${flux.passed?'通过':'尚未通过'}</b>；合力向量最大差异 ${fmt(Math.max(...flux.cuts.map(x=>x.forceRelativeDifference))*100)}%，合矩向量最大差异 ${fmt(Math.max(...flux.cuts.map(x=>x.momentRelativeDifference))*100)}%。此项直接积分恢复出的应力，不读取预先施加的切口节点力。</p>`;
    const c=r.cutLengthVerification;if(!c||c.jobId!==r.jobId||c.fingerprint!==r.fingerprint)return;$('#localCharts').innerHTML+=`<h3>截取距离检查：${c.converged?'通过':'尚未通过'}</h3><p>${escape(c.criterion)}</p><p>${c.levels.map(x=>`${fmt(x.cutLengthM)} m：${fmt(x.toeMPa)} MPa`).join('；')}</p><p>固定位置分布最大变化 ${fmt(c.maximumProfileChange*100)}%；区域峰值最大变化 ${fmt(c.maximumPeakChange*100)}%。</p>`;$('#localReport').innerHTML=$('#localReport').innerHTML.replace('截断距离：未比较',`截断距离：${c.converged?'通过':'尚未通过'}`);
  }
  function renderLine(r){
    const v=r.validation,s=r.result,paths=r.samplingPaths||{},support=v.idealSupport;
    const title=r.analysisType==='idealClamp'?'圆管理想固支端':'连续圆管加载杆段（无球形节点、无焊缝）';
    $('#localReport').innerHTML=`<h2>${title}</h2><p>N${r.node} · ${s.nodeCount.toLocaleString()} 网格节点 · ${s.elementCount.toLocaleString()} 曲边 Tet10；截取 ${fmt(s.cutLength)} m</p><p>数值残差与平衡：${v.numericalPassed?'通过':'未通过'}；01切口合力/合矩传递：${v.boundaryTransferPassed?'通过':'未通过'}</p><p>固定关注区域未平均应力峰值 ${fmt(Math.max(...Object.values(paths).map(x=>x.nodePeakMisesPa))/1e6)} MPa；全模型未平均峰值 ${fmt(s.maximumElementNodalMisesPa/1e6)} MPa。</p><p>${escape(r.stressDefinition)}</p>${support?`<p>固定面 ${support.fixedNodeCount} 个节点，最大位移 ${fmt(support.maximumFixedDisplacementM)} m；与01反力差：合力 ${fmt(support.forceRelativeDifference*100)}%，合矩 ${fmt(support.momentRelativeDifference*100)}%。</p>`:`<p>面片宽度 ${fmt(r.localRequest.geometry.patchWidth*1000)} mm，周向 ${fmt(r.localRequest.geometry.patchAngleDegrees)}°；只分配力，不强制加载区刚化。</p>`}<details><summary>建模假设</summary>${r.warnings.map(escape).join('<br>')}</details>`;
    $('#localReport').insertAdjacentHTML('afterbegin',`<span class="lr-badge">已求解 · 验证状态分列</span><p class="lr-notice">${escape(note)}</p>`);
    $('#hubDownloads').disabled=busy;$('#exportLocalFigure').disabled=busy;$('#legendText').textContent='连续圆管节点平均 Mises；固定区域按未平均应力验证';
    const c=r.lineMeshVerification;$('#localCharts').innerHTML=c?`<h3>固定杆段区域网格检查：${c.converged?'通过':'尚未通过'}</h3><p>${escape(c.criterion)}</p><p>${c.levels.map(x=>`${fmt(x.toeSizeM*1000)} mm：${fmt(x.toeMPa)} MPa`).join('；')}</p><p>末两档峰值变化 ${fmt(c.lastPair.toe.peakRelativeChange*100)}%；固定位置最大变化 ${fmt(c.lastPair.toe.profileMaxRelativeChange*100)}%。</p>`:'<p>当前结果为单档网格，固定关注区域网格检查未比较。</p>';
    appendCutStudy(r);window.frameCAERefreshVisualWorkbench?.();
  }
  function refresh(){
    couplingControl.hidden=!active();analysisControl.hidden=!active();
    shearControl.hidden=!active()||$('#solidCouplingMode').value!=='forceSubmodel';
    taskControl.hidden=!active();
    selector.disabled=false;$('#abaqusHubSettings').hidden=!isB();fresh.hidden=!active();
    selector.querySelector('option[value="standalone"]').disabled=!isB();
    if(!isB()&&selector.value==='standalone')selector.value='auto';
    if(isB()&&!['standalone','abaqus'].includes(selector.value))selector.value='standalone';
    if(!active()){cancel.hidden=true;window.frameCAERefreshAbaqusPanel?.();if(!isB())window.FrameCAESolidView?.hide();return;}
    $('#genericWeldLeg').closest('label').hidden=true;$('#genericCutRatio').closest('label').hidden=true;
    $('#runGeneric').textContent='计算局部应力';$('#runGenericConvergence').textContent='加密一档检查';
    $('#weldedConnectionSettings .weld-badge').textContent='B 一体节点件＋环形对接焊';
    const analysisType=$('#solidAnalysisType').value,isLine=['continuousPipe','idealClamp'].includes(analysisType);
    mode.closest('label').hidden=isLine;
    $('#genericShowWeld').closest('label').hidden=isLine;
    $('#abaqusHubSettings h4').textContent=isLine?'连续圆管与关注区域网格':'一体节点件与全熔透环焊缝';
    $('#hubToeSize').closest('label').firstChild.textContent=isLine?'关注区细网格 / m':'焊趾网格 / m';
    if(isLine){$('#runGenericConvergence').textContent='加密一档检查';$('#weldedConnectionSettings .weld-badge').textContent=analysisType==='idealClamp'?'圆管理想固支端':'连续直圆管 · 无新增焊缝';}
    for(const id of ['hubRadius','hubBlend','hubWeldDistance','hubWeldWidth','hubReinforcement','genericToeRadius','hubLoadRadius','hubLoadDirection'])$('#'+id).closest('label').hidden=isLine;
    $('#genericWeldHint').hidden=true;
    const help=$('#abaqusHubSettings > .help');if(help)help.textContent=isLine?'自编曲边 Tet10 连续空心圆管；不增加球形节点或焊缝。理想固支采用端面位移约束，边缘峰值与固定关注区域的收敛结果分别列出。':'自编曲边 Tet10：支持 1–8 根同材料圆管，可异径、异壁厚在非支座节点以任意夹角连接，适用于 T、Y、K、X 等拓扑。全熔透环焊缝与母材弹性参数相同；不含热过程、残余应力或缺陷。';
    const boundaryHelp=$('#abaqusHubSettings > p.help:nth-of-type(2)');if(boundaryHelp)boundaryHelp.textContent='01提供切口合力和合矩；局部模型内的节点外载与保留杆段均布载荷另行传递，位移仅确定刚体姿态。';
    const overview=$('#weldedConnectionSettings > p.help:not(#genericWeldHint)');if(overview)overview.textContent='当前采用01截面内力驱动。切口合力、合矩与局部直接载荷均按统一的全局XYZ传递；网格和截取距离分别验证。';
    render();
  }
  async function applyJob(id,pending){
    let state;while(true){state=await api(path(id));note=state.message+(state.iteration?` · 迭代 ${state.iteration}`:'');links(state.files||[]);render();$('#status').textContent=note;
      if(state.state==='failed'||state.state==='cancelled')throw Error(state.message);
      if(state.state==='completed')break;await new Promise(resolve=>setTimeout(resolve,1200));}
    const answer=await api(path(id,'/result'));
    if(signature()!==pending)throw Error('计算期间输入已改变；结果已保存，但未套用到当前模型。');
    localResult=answer;accepted=pending;displayMode='local';note='本次独立求解已完成，云图显示真实曲面网格；各验证状态分别列出。';draw();render();
    $('#results').textContent=JSON.stringify({jobId:id,result:answer.result,validation:answer.validation},null,2);
  }
  async function run(study){
    if(!active())return (study?old.runGenericConvergence:old.runGeneric)?.();if(busy)return;
    if(!result){failure='请先完成 01 整体求解。';render();return;}
    const pending=signature();failure='';pendingCancel=false;localResult=null;displayMode='global';draw();setBusy(true);render();
    try{
      const request={...requestBody(),force:$('#solidForceRerun').checked};
      if(study)request.study={toeSizes:singleRefinementSizes($('#hubToeSize').value)};
      const submitted=await api('/api/solid-local/jobs',request);job=submitted.jobId;$('#hubSavedJob').value=job;
      if(pendingCancel){await api(path(job,'/cancel'),{});throw Error('计算已取消。');}
      await applyJob(job,pending);
    }catch(e){failure=e.message;}finally{setBusy(false);render();}
  }
  $('#runGeneric').onclick=()=>run(false);$('#runGenericConvergence').onclick=()=>run(true);
  cancel.onclick=async()=>{pendingCancel=true;cancel.disabled=true;if(job)await api(path(job,'/cancel'),{});};
  async function preview(){
    if(!active())return old.hubPreview?.();failure='';
    try{const q=await api('/api/solid-local/prepare',requestBody());note=`N${q.node} · ${q.arms.map(a=>'E'+a.element).join('、')} · 节点 F/M=(${q.load.wrench.join(', ')})；切口内力来自当前 01，截面一致性已核对。`;$('#hubArmSummary').textContent=q.arms.map(a=>`E${a.element}：方向 (${a.direction.join(', ')})；切口 ${a.length} m`).join('；');}catch(e){failure=e.message;}render();
  }
  $('#hubPreview').onclick=preview;
  async function identify(auto){
    if(!active())return (auto?old.autoGeneric:old.selectedGeneric)?.();
    try{
      const q=await api('/api/solid-local/suggest',{model:payload(),globalSolution:globalSolution(),...(auto?{}:{node:Number($('#genericNode').value)}),couplingMode:$('#solidCouplingMode').value,shearDistribution:$('#solidShearDistribution').value});
      applySettings({...q.settingsSnapshot,...q.geometry,node:q.node,meshSize:q.mesh.size,focusSize:q.mesh.focusSize,toeSize:q.mesh.toeSize,cutLength:q.arms[0].length,loadRadius:q.load.radius,loadDirection:q.load.direction});
      identifiedModel=JSON.stringify(payload());await preview();
    }catch(e){failure=e.message;render();}
  }
  $('#selectedGeneric').onclick=()=>identify(false);$('#autoGeneric').onclick=()=>identify(true);
  $('#hubRestore').onclick=async()=>{
    if(!active())return old.hubRestore?.();try{
      failure='';job=$('#hubSavedJob').value.trim();const answer=await api(path(job,'/result'));const current=await api('/api/solid-local/prepare',requestBody());
      if(!FrameCAEModelView.localProblemMatches(answer.localRequest,current))throw Error('保存作业与当前模型/截面运动/几何或网格不匹配。');
      await applyJob(job,signature());
    }catch(e){failure=e.message;render();}
  };
  $('#solidImportTask').onclick=()=>$('#solidTaskFile').click();
  $('#solidTaskFile').onchange=async event=>{
    const file=event.target.files[0];if(!file)return;
    try{
      failure='';const saved=JSON.parse(await file.text()),q=saved.localRequest;
      const settings=q?{...q.geometry,...q.settingsSnapshot,node:q.node,couplingMode:q.couplingMode,shearDistribution:q.shearDistribution||'resultantAffine',cutLength:q.arms[0].length,meshSize:q.mesh.size,focusSize:q.mesh.focusSize,toeSize:q.mesh.toeSize,loadRadius:q.load.radius,loadDirection:q.load.direction}:{...saved.settings,shearDistribution:saved.settings?.shearDistribution||'resultantAffine'};
      if(!settings)throw Error('03文件缺少settings参数。');
      window.FrameCAEArchiveJobId=saved.jobId||null;const current=await api('/api/solid-local/prepare',{model:payload(),settings,globalSolution:globalSolution(),archiveJobId:saved.jobId||null});
      const fingerprint=q?.globalSolutionAudit?.modelFingerprint||saved.modelFingerprint;
      if(!fingerprint||fingerprint!==current.globalSolutionAudit.modelFingerprint)throw Error('03参数文件与当前01模型不一致，请先导入对应模型并完成01。');
      applySettings({...current.geometry,...current.settingsSnapshot,node:current.node,couplingMode:current.couplingMode,shearDistribution:current.shearDistribution||'resultantAffine',cutLength:current.arms[0].length,meshSize:current.mesh.size,focusSize:current.mesh.focusSize,toeSize:current.mesh.toeSize,loadRadius:current.load.radius,loadDirection:current.load.direction});
      note='03参数已载入，可用自编程序重新计算。';
      if(saved.jobId){
        $('#hubSavedJob').value=saved.jobId;let answer;
        try{answer=await api(path(saved.jobId,'/result'));}catch(_){note='03参数已载入，本机未找到保存作业；点击计算可生成结果。';}
        if(answer){if(!FrameCAEModelView.localProblemMatches(answer.localRequest,current))throw Error('保存结果与03参数不匹配。');job=saved.jobId;await applyJob(job,signature());}
      }
    }catch(e){failure=e.message;}finally{event.target.value='';render();}
  };
  $('#solidExportTask').onclick=async()=>{
    try{const q=await api('/api/solid-local/prepare',requestBody());download('FrameCAE_N'+q.node+'_03参数.json',JSON.stringify({schemaVersion:1,kind:'FrameCAE03Task',modelFingerprint:q.globalSolutionAudit.modelFingerprint,settings:{...q.geometry,...q.settingsSnapshot,node:q.node,couplingMode:q.couplingMode,shearDistribution:q.shearDistribution||'resultantAffine',cutLength:q.arms[0].length,meshSize:q.mesh.size,focusSize:q.mesh.focusSize,toeSize:q.mesh.toeSize,loadRadius:q.load.radius,loadDirection:q.load.direction},jobId:accepted===signature()?localResult?.jobId||null:null},null,2),'application/json');}catch(e){failure=e.message;render();}
  };
  $('#hubDownloads').onclick=()=>active()?localResult&&download('FrameCAE_N'+localResult.node+'_自编有限元结果.json',JSON.stringify(localResult,null,2),'application/json'):old.hubDownloads?.();
  $('#exportLocalFigure').onclick=()=>active()?FrameCAESolidView.export():old.exportLocalFigure?.();
  for(const id of ['hubCut','genericMeshSize','hubFocus','hubToeSize'])$('#'+id).value=({hubCut:'.8',genericMeshSize:'.025',hubFocus:'.01',hubToeSize:'.004'})[id];
  $('#genericCoarseSize').value='.004';$('#genericFineSize').value='.001';
  function backendChanged(){
    if(localResult?.kind==='standaloneIntegralHub'&&(!isB()||selector.value!=='standalone')){localResult=null;accepted='';displayMode='global';draw();}
    if(localResult?.kind==='abaqusIntegralHub'&&selector.value==='standalone'){localResult=null;displayMode='global';draw();}
    refresh();
  }
  $('#solidCouplingMode').addEventListener('change',refresh);$('#solidShearDistribution').addEventListener('change',render);selector.addEventListener('change',backendChanged);mode.addEventListener('change',backendChanged);
  $('#solidAnalysisType').addEventListener('change',refresh);
  window.addEventListener('framecae-module-change',()=>{refresh();if(active()&&document.body.dataset.module==='local'&&window.frameCAEHasConfirmedModel?.()&&identifiedModel!==JSON.stringify(payload()))identify(true);});
    $('#genericNode').addEventListener('change',()=>{$('#solidAnalysisType').value='auto';if(active()&&window.frameCAEHasConfirmedModel?.())identify(false);});window.addEventListener('framecae:model-state',render);
  setInterval(()=>{if(!active()||!accepted||signature()===accepted)return;accepted='';if(localResult?.kind==='standaloneIntegralHub'){localResult=null;displayMode='global';draw();}note='输入已修改，旧结果已失效，请重新计算。';render();},700);
  window.FrameCAESolidPanel={render,refresh,run,signature,applySettings};refresh();
  const requestedJob=new URL(location.href).searchParams.get('solidJob');
  if(requestedJob)window.addEventListener('load',async()=>{
    try{
      if(!/^[0-9a-f]{32}$/.test(requestedJob))throw Error('作业编号无效。');
      await new Promise(resolve=>{const ready=()=>{if(result?.elements?.length&&data?.nodes?.length)resolve();else setTimeout(ready,100);};ready();});
      const saved=await api(path(requestedJob,'/result')),q=saved.localRequest;
      const ids={node:'genericNode',hubRadius:'hubRadius',blendWidth:'hubBlend',cutLength:'hubCut',weldDistance:'hubWeldDistance',weldWidth:'hubWeldWidth',reinforcement:'hubReinforcement',toeRadius:'genericToeRadius',meshSize:'genericMeshSize',focusSize:'hubFocus',toeSize:'hubToeSize',loadRadius:'hubLoadRadius'};
      for(const [key,id] of Object.entries(ids))if(q.settingsSnapshot[key]!==undefined)$('#'+id).value=q.settingsSnapshot[key];
      if(saved.verificationStudy?.cases?.length){$('#genericCoarseSize').value=saved.verificationStudy.cases[0].toeSizeM;$('#genericFineSize').value=saved.verificationStudy.cases.at(-1).toeSizeM;}
      applySettings({couplingMode:q.couplingMode||'forceSubmodel',shearDistribution:q.shearDistribution||'resultantAffine',loadDirection:q.load.direction});
      const current=await api('/api/solid-local/prepare',requestBody());
      if(!FrameCAEModelView.localProblemMatches(q,current))throw Error('保存结果与当前网页模型不同，未替换模型；请手动核对输入。');
      if(!window.frameCAEHasConfirmedModel?.())await window.frameCAEConfirmModel();
      $('#workspaceSidebar [data-module="local"]').click();$('#hubSavedJob').value=requestedJob;$('#hubRestore').click();
    }catch(e){failure=e.message;render();}
  },{once:true});
})();

/* Presentation-only simplification. Keep controls and their IDs for existing
   imports, archive restoration, validation and solver event handlers. */
(() => {
  if(typeof document==='undefined')return;
  const $=s=>document.querySelector(s),panel=$('#genericLocalSettings'),report=$('#localReport');
  if(!panel||!report)return;
  const style=document.createElement('style');
  style.textContent='.local-ui-suppressed{display:none!important}#genericLocalSettings .local-mesh-check-note{font-size:12px;color:#607286;margin:8px 0}#localReport .lr-card [title]{cursor:help}';
  document.head.append(style);
  const hide=el=>el?.classList.add('local-ui-suppressed');
  const text=(el,value)=>{if(el&&el.textContent!==value)el.textContent=value;};
  for(const id of ['selectedGeneric','genericLocalHint','hubNodeIdentity','hubUnifySections','hubPreview','hubDownloads','hubRestore','hubJobFiles','hubArmSummary','genericConvergenceHint','visualLocalNotice'])hide($('#'+id));
  for(const id of ['genericConnectionType','genericSolverMethod','hubSavedJob','solidCouplingMode','solidShearDistribution'])hide($('#'+id)?.closest('label'));
  // Keep the baseline mesh size visible: it is an input to the local solver.
  hide($('#genericCoarseSize')?.closest('.local-grid'));
  hide($('#solidAnalysisType')?.parentElement);
  hide($('#solidImportTask')?.parentElement.querySelector('small'));
  hide($('#weldedConnectionSettings > h4'));
  for(const el of panel.querySelectorAll('#abaqusHubSettings > p.help,#weldedConnectionSettings > p.help,.local-workflow-step > p.help'))hide(el);
  for(const button of panel.querySelectorAll('button'))if(/恢复.*(?:参数|初始)|查看.*验证算例/.test(button.textContent))hide(button);
  text($('#autoGeneric'),'自动选择受力较大节点');
  const convergence=$('#runGenericConvergence')?.closest('details');
  hide(convergence);
  const loadNotes={
    hubLoadRadius:['承载面投影半径 / m','节点集中力或力矩的等效加载面大小；不是管半径。'],
    hubLoadDirection:['承载面朝向','选择节点件上加载面的位置朝向；荷载本身的方向和大小仍来自01。']
  };
  for(const [id,[label,help]] of Object.entries(loadNotes)){
    const input=$('#'+id),parent=input?.closest('label');
    if(parent?.firstChild?.nodeType===3)parent.firstChild.textContent=label;
    if(parent)parent.title=help;if(input)input.title=help;
  }
  const unaveraged='相邻单元在共同节点的应力分别保留，不跨单元平均，再取最大值。';
  function cleanReport(){
    if(!window.frameCAEUseStandaloneLocal?.())return;
    const badge=report.querySelector('.lr-badge'),failed=Boolean(report.querySelector('.lr-badge.error'));
    const running=Boolean(badge?.textContent.includes('正在'));
    if(badge?.textContent==='已求解 · 验证状态分列')text(badge,'已求解');
    hide(report.querySelector('.lr-head > div > p'));
    for(const notice of report.querySelectorAll(':scope > .lr-notice')){
      const hideNotice=!failed&&!running;
      notice.classList.toggle('local-ui-suppressed',hideNotice);
      if(failed)notice.setAttribute('role','alert');
    }
    for(const p of report.querySelectorAll(':scope > p')){
      if(/^(数值平衡\/残差|相对残差|切口剪力分布|圣维南载荷传递检查)/.test(p.textContent.trim()))hide(p);
    }
    for(const details of report.querySelectorAll('details')){
      const summary=details.querySelector('summary');
      if(summary?.textContent==='本次模型假设与适用范围')hide(details);
      if(summary?.textContent==='各杆q、加载区间与守恒/虚功检查')hide(details);
      if(summary&&/^切口(?:载荷|反力)/.test(summary.textContent)){
        hide(details);
        text(summary,'切口载荷核对');
        text(details.querySelector('p'),'核对01切口内力与03实体所承受的合力、合矩是否一致。');
      }
    }
    const cards=report.querySelectorAll('.lr-cards .lr-card');
    for(const card of cards){
      const label=card.querySelector('span'),detail=card.querySelector('small');
      if(label?.textContent==='焊趾未平均最大值'){
        text(label,'焊趾峰值应力');label.title=unaveraged;
        text(detail,'保留单元各自应力，取最大值');
      }
      if(label?.textContent==='全模型未平均最大值'){
        text(label,'局部模型峰值应力');label.title=unaveraged;
      }
    }
    for(const th of report.querySelectorAll('th'))if(th.textContent==='未平均峰值 / MPa'){text(th,'峰值应力 / MPa');th.title=unaveraged;}
    const charts=$('#localCharts');
    if(charts){
      const heading=charts.querySelector('h3');
      if(heading?.textContent==='验证范围')charts.replaceChildren();
      if(heading?.textContent==='本次固定焊趾路径网格检查'){
        text(heading,'网格加密对比');
        const description=charts.querySelector('p');
        if(localResult?.verificationStudy?.cases?.length===2&&description&&!description.textContent.endsWith('本次为相邻两档对比。'))text(description,description.textContent+' 本次为相邻两档对比。');
      }
      for(const title of charts.querySelectorAll('h3')){
        if(!/^(本结果的焊趾与肩部网格研究|截取距离检查：)/.test(title.textContent))continue;
        for(let el=title;el&&(el===title||el.tagName!=='H3');el=el.nextElementSibling)hide(el);
      }
      charts.classList.toggle('local-ui-suppressed',[...charts.children].every(el=>el.classList.contains('local-ui-suppressed')));
    }
  }
  let pending=false;
  const refresh=()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;cleanReport();});};
  new MutationObserver(refresh).observe(report,{childList:true,subtree:true,characterData:true});
  new MutationObserver(refresh).observe($('#localCharts'),{childList:true,subtree:true,characterData:true});
  $('#hubToeSize')?.addEventListener('input',refresh);
  window.addEventListener('framecae-module-change',refresh);
  window.FrameCAELocalPresentation={refresh,unaveraged,version:'03-ui-20261020-no-parameter-images'};
  refresh();
})();

