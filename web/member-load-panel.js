/* Extend the existing member-load table; one schema for import, edit and export. */
(() => {
  const schema=schemas.memberLoads;
  schema.title='杆件均布线荷载 q（整杆恒定；N/m）/ 杆内集中力（N）';
  schema.fields=[['element','杆件编号'],['type','荷载类型'],['coordinateSystem','坐标系'],['position','集中力位置 x / m'],['qx','qx / N/m（集中力为N）'],['qy','qy / N/m（集中力为N）'],['qz','qz / N/m（集中力为N）'],['unit','单位']];
  schema.blank={element:1,type:'uniform',coordinateSystem:'global',position:'',qx:0,qy:0,qz:0,unit:'N/m'};
  const previousRow=makeRow;
  makeRow=function(name,s,row,index){
    const tr=previousRow(name,s,row,index);if(name!=='memberLoads')return tr;
    tr.dataset.memberLoadRow=String(index);
    const fields=Object.fromEntries(s.fields.map(([key],i)=>[key,tr.children[i]]));
    for(const [key,options,initial] of [
      ['type',[['uniform','整杆均布 q'],['point','杆内集中力']],row.type||'uniform'],
      ['coordinateSystem',[['global','全局 XYZ'],['local','杆件局部 xyz（起点→终点）']],row.coordinateSystem||'local']]){
      const select=document.createElement('select');select.dataset.memberField=key;
      for(const [value,text] of options)select.add(new Option(text,value));select.value=initial;
      select.oninput=()=>{data.memberLoads[index][key]=select.value;update();};
      fields[key].replaceChildren(select);
    }
    const update=()=>{
      const uniform=fields.type.firstChild.value==='uniform';
      fields.position.firstChild.disabled=uniform;
      fields.position.firstChild.title=uniform?'均布载荷覆盖整根杆件，无需位置':'从杆件起点量起，单位m';
      fields.unit.firstChild.value=uniform?'N/m':'N';fields.unit.firstChild.readOnly=true;
      // Missing coordinateSystem in old files still means local. Only persist
      // explicit defaults when the user edits this row.
      if(tr.isConnected)data.memberLoads[index].unit=uniform?'N/m':'N';
    };
    for(const key of ['element','position','qx','qy','qz']){
      const input=fields[key].firstChild;input.type='number';input.step='any';input.dataset.memberField=key;
      input.addEventListener('input',()=>{data.memberLoads[index].unit=fields.type.firstChild.value==='uniform'?'N/m':'N';});
    }
    update();return tr;
  };
  const editor=document.createElement('div');editor.id='builderMemberLoads';
  editor.innerHTML='<hr><strong>杆件均布线荷载 q / N/m</strong><label>杆件 <select id="builderQElement"></select></label><label>坐标系 <select id="builderQCoordinate"><option value="global">全局 XYZ</option><option value="local">杆件局部 xyz</option></select></label><label>qx (N/m) <input id="builderQx" type="number" step="any" value="0"></label><label>qy (N/m) <input id="builderQy" type="number" step="any" value="0"></label><label>qz (N/m) <input id="builderQz" type="number" step="any" value="0"></label><button id="builderApplyQ" type="button" class="secondary">创建／更新该杆q</button><p id="builderQHint" class="help">整根杆上的恒定线荷载；方向和起终点与杆件表一致。</p>';
  (document.querySelector('#builderToolPanel2')||document.querySelector('#builderSelection').parentElement).append(editor);
  const $=id=>document.getElementById(id);
  function fillQ(){
    const id=Number($('builderQElement').value),rows=(data.memberLoads||[]).filter(r=>Number(r.element)===id&&r.type==='uniform');
    const row=rows[0];$('builderQCoordinate').value=row?(row.coordinateSystem||'local'):'global';
    for(const k of ['x','y','z'])$('builderQ'+k).value=row?.['q'+k]??0;
    $('builderApplyQ').disabled=!(data.elements||[]).some(e=>Number(e.id)===id);
    $('builderQHint').textContent=rows.length>1?'该杆有多条均布荷载；这里只编辑第一条，其余条目在下方杆件荷载表保留并叠加。':'保存后在画布显示紫色均布荷载箭头；可叠加节点荷载、自重。';
  }
  function refreshQ(){
    const previous=$('builderQElement').value;
    $('builderQElement').replaceChildren(...(data.elements||[]).map(e=>new Option('E'+e.id+'：N'+e.start+'→N'+e.end,e.id)));
    if([...$('builderQElement').options].some(o=>o.value===previous))$('builderQElement').value=previous;
    fillQ();
  }
  $('builderQElement').onchange=fillQ;
  $('builderApplyQ').onclick=()=>{
    const id=Number($('builderQElement').value),values=['x','y','z'].map(k=>Number($('builderQ'+k).value));
    if(!values.every(Number.isFinite))return;
    data.memberLoads||=[];let row=data.memberLoads.find(r=>Number(r.element)===id&&r.type==='uniform');
    if(!row){row={element:id,type:'uniform',position:null};data.memberLoads.push(row);}
    Object.assign(row,{qx:values[0],qy:values[1],qz:values[2],coordinateSystem:$('builderQCoordinate').value,unit:'N/m'});
    window.frameCAEInvalidateModel?.();renderTables();
    window.dispatchEvent(new Event('framecae:loads-updated'));
  };
  window.addEventListener('framecae:selection',()=>{
    const id=window.frameCAESelectedElement?.();if(id!=null){$('builderQElement').value=String(id);fillQ();}
  });
  const oldTables=renderTables;
  renderTables=function(){
    oldTables();
    const add=document.querySelector('[data-add="memberLoads"]');if(!add)return;
    const section=add.closest('details');section.id='memberLoadSettings';
    section.insertAdjacentHTML('beforeend','<p class="help">q为单位杆轴实际长度上的力，单位N/m；可与节点集中荷载、自重叠加。局部x由杆件起点指向终点，局部y/z沿用原有定义。未标坐标系的旧文件仍按局部坐标解释；多行同杆荷载相加。修改后请重新确认并计算01。</p>');
    if((data.memberLoads||[]).length)section.open=true;
    refreshQ();
  };
  renderTables();
  document.querySelector('#selfWeightSettings')?.addEventListener('input',()=>window.frameCAEInvalidateModel?.());
  // No Abaqus run in this round; retained APIs/source can be re-enabled by the
  // backend feature switch, without removing a colleague's verification code.
  fetch('/api/features').then(r=>r.json()).then(features=>{
    if(features.abaqusVerificationEnabled)return;
    for(const id of ['avGenerate','avSolve','avViewer','avRestore']){
      const el=document.getElementById(id);if(el){el.disabled=true;el.title='本轮暂不纳入Abaqus验算';}
    }
    const option=document.querySelector('#genericSolverMethod option[value="abaqus"]');
    if(option){option.disabled=true;option.textContent='Abaqus（本轮禁用，代码保留）';}
    const state=document.getElementById('avStatus');if(state)state.textContent='本轮已禁用Abaqus验算；03采用自编求解器。';
  }).catch(()=>{});
})();
