/* Shared 03 WebGL surface view: physical global XYZ, real curved FE boundary. */
(() => {
  const canvas=document.querySelector('#scene');if(!canvas||!window.Plotly)return;
  const host=document.createElement('div');host.id='solidInteractiveView';host.hidden=true;
  host.innerHTML=`<div class="solid-view-tools"><label>视图 <select id="solidViewMode"><option value="stress">应力云图</option><option value="mesh">表面网格</option><option value="global">在整体框架中定位</option></select></label><button id="solidIso" type="button">等轴测</button><button id="solidTop" type="button">俯视 Z</button><button id="solidAlongX" type="button">沿 X</button><button id="solidAlongY" type="button">沿 Y</button><label><input id="solidLoads" type="checkbox" checked> 荷载示意</label><label><input id="solidPeaks" type="checkbox" checked> 焊趾峰值</label><label><input id="solidDeform" type="checkbox"> 变形 ×10</label><span>左键旋转 · 滚轮缩放 · 右键平移</span></div><div id="solidXYZPlot" aria-label="局部实体应力交互三维图，全局 XYZ 坐标，单位米"></div>`;
  canvas.after(host);const plot=host.querySelector('#solidXYZPlot');
  const style=document.createElement('style');style.textContent=`#solidInteractiveView{position:relative;background:#fff;min-width:0;width:100%}#solidInteractiveView[hidden]{display:none!important}.solid-view-tools{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid #dce4ee;font-size:12px}.solid-view-tools label{display:flex;align-items:center;gap:4px}.solid-view-tools button,.solid-view-tools select{padding:5px 8px;width:auto;min-height:30px}.solid-view-tools input{width:auto}.solid-view-tools span{color:#607286;margin-left:auto}#solidXYZPlot{width:100%;height:620px;min-width:0}@media(max-width:650px){#solidXYZPlot{height:470px}.solid-view-tools span{width:100%;margin-left:0}}`;
  document.head.append(style);let shown=null,drawKey='',wire=null,pending=false,lastCamera=null;
  const initialCamera=()=>({eye:{x:1.5,y:-1.65,z:1.1},up:{x:0,y:0,z:1}});
  function show(answer){shown=answer;canvas.style.display='none';host.hidden=false;window.frameCAERefreshVisualWorkbench?.();const oldCamera=document.querySelector('#visualCamera');if(oldCamera)oldCamera.style.display='none';queue();}
  function hide(){host.hidden=true;canvas.style.display='';const oldCamera=document.querySelector('#visualCamera');if(oldCamera)oldCamera.style.display='';}
  function queue(){if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;render().catch(e=>{document.querySelector('#error').textContent=e.message;document.querySelector('#error').style.display='block';});});}
  function makeWire(mesh,xyz){
    if(wire?.job===shown.jobId)return wire.trace;
    const set=new Set(),x=[],y=[],z=[];
    for(const t of mesh.tri6)for(const [a,m,b] of [[t[0],t[3],t[1]],[t[1],t[4],t[2]],[t[2],t[5],t[0]]]){
      const key=Math.min(a,b)+','+Math.max(a,b);if(set.has(key))continue;set.add(key);
      for(const n of [a,m,b]){x.push(xyz[n][0]);y.push(xyz[n][1]);z.push(xyz[n][2]);}x.push(null);y.push(null);z.push(null);
    }
    const trace={type:'scatter3d',mode:'lines',x,y,z,line:{color:'#354b60',width:1},hoverinfo:'skip',name:'实际曲边单元边'};wire={job:shown.jobId,trace};return trace;
  }
  async function render(){
    if(!shown||host.hidden)return;
    const mode=document.querySelector('#solidViewMode').value,deform=document.querySelector('#solidDeform').checked&&mode==='stress',peaks=document.querySelector('#solidPeaks').checked;
    document.querySelector('#solidDeform').disabled=mode!=='stress';if(mode!=='stress')document.querySelector('#solidDeform').checked=false;
    const key=JSON.stringify([shown.jobId,mode,deform,peaks,document.querySelector('#solidLoads').checked]);if(drawKey===key&&plot.data?.length){Plotly.Plots.resize(plot);return;}
    if(shown.jobId!==plot.dataset.jobId){lastCamera=null;wire=null;}
    const m=shown.mesh,origin=shown.origin;
    const xyz=m.nodes.map((p,i)=>p.map((v,k)=>v+origin[k]+(deform?10*m.displacement[i][k]:0)));
    const traces=[{type:'mesh3d',x:xyz.map(p=>p[0]),y:xyz.map(p=>p[1]),z:xyz.map(p=>p[2]),i:m.faces.map(f=>f[0]),j:m.faces.map(f=>f[1]),k:m.faces.map(f=>f[2]),intensity:m.nodalMisesMPa,cmin:0,cmax:shown.result.maximumNodalAveragedMisesPa/1e6,colorscale:[[0,'#2442a4'],[.25,'#15b7cb'],[.5,'#70cc54'],[.75,'#f2d84b'],[1,'#d93338']],colorbar:{title:{text:'σVM / MPa'},thickness:14},opacity:mode==='mesh'?.25:1,flatshading:false,lighting:{ambient:.65,diffuse:.7,specular:.2},name:'N'+shown.node,hovertemplate:'全局 X=%{x:.4f} m<br>全局 Y=%{y:.4f} m<br>全局 Z=%{z:.4f} m<br>σVM 平均=%{intensity:.3f} MPa<extra></extra>'}];
    if(mode==='mesh')traces.push(makeWire(m,xyz));
    if(peaks&&!deform){
      const all=Object.entries(shown.toePaths||{});const peak=all.reduce((a,b)=>!a||b[1].nodePeakMisesPa>a[1].nodePeakMisesPa?b:a,null);
      if(peak){const p=peak[1].peakPoint.map((v,k)=>v+origin[k]);traces.push({type:'scatter3d',mode:'markers+text',x:[p[0]],y:[p[1]],z:[p[2]],marker:{color:'#9a418b',symbol:'cross',size:3},text:[peak[0].replace('_near',' 近节点侧').replace('_far',' 远节点侧')+' '+(peak[1].nodePeakMisesPa/1e6).toFixed(3)+' MPa'],textposition:'top center',textfont:{size:12,color:'#76376b'},name:'未平均焊趾峰值',hovertemplate:'未跨单元平均峰值<extra></extra>'});}
    }
    traces.push({type:'scatter3d',mode:'text',x:[origin[0]],y:[origin[1]],z:[origin[2]+shown.localRequest.geometry.hubRadius+.025],text:['N'+shown.node],textfont:{size:17,color:'#24364c'},name:'节点标识',hoverinfo:'skip'});
    if(mode==='global'){
      const model=shown.modelSnapshot,byId=new Map(model.nodes.map(n=>[Number(n.id),n]));let x=[],y=[],z=[];
      for(const e of model.elements){for(const id of [e.start,e.end]){const n=byId.get(Number(id));x.push(n.x);y.push(n.y);z.push(n.z);}x.push(null);y.push(null);z.push(null);}
      traces.push({type:'scatter3d',mode:'lines',x,y,z,line:{color:'#697e92',width:4},hoverinfo:'skip'});
      traces.push({type:'scatter3d',mode:'markers+text',x:model.nodes.map(n=>n.x),y:model.nodes.map(n=>n.y),z:model.nodes.map(n=>n.z),text:model.nodes.map(n=>'N'+n.id),textposition:'top center',marker:{size:3,color:'#697e92'},hoverinfo:'text'});
    }
    if(document.querySelector('#solidLoads').checked){
      const model=mode==='global'?shown.modelSnapshot:FrameCAEModelView.localLoadModel(shown);
      const span=Math.max(...['x','y','z'].map(k=>Math.max(...model.nodes.map(n=>n[k]))-Math.min(...model.nodes.map(n=>n[k]))),.01);
      traces.push(...FrameCAEModelView.loadTraces(model,span,mode==='global'?'':'（等效线载荷）'));
    }
    await Plotly.react(plot,traces,{margin:{l:0,r:0,t:15,b:0},paper_bgcolor:'#fff',showlegend:false,uirevision:shown.jobId,scene:{aspectmode:'data',dragmode:'orbit',camera:lastCamera||initialCamera(),xaxis:{title:{text:'全局 X / m'},showgrid:true,zeroline:true},yaxis:{title:{text:'全局 Y / m'},showgrid:true,zeroline:true},zaxis:{title:{text:'全局 Z / m'},showgrid:true,zeroline:true}}},{responsive:true,displaylogo:false,scrollZoom:true,toImageButtonOptions:{format:'png',filename:'FrameCAE_N'+shown.node+'_XYZ应力云图',width:1500,height:1100,scale:1}});
    if(!plot.dataset.events){plot.on('plotly_relayout',e=>{if(e['scene.camera'])lastCamera=e['scene.camera'];});plot.dataset.events='yes';}
    drawKey=key;plot.dataset.jobId=shown.jobId;window.frameCAESolidViewReady=true;
  }
  for(const id of ['solidViewMode','solidPeaks','solidDeform','solidLoads'])document.querySelector('#'+id).addEventListener('change',()=>{drawKey='';queue();});
  document.querySelector('#visualMesh')?.addEventListener('change',event=>{if(!host.hidden){document.querySelector('#solidViewMode').value=event.target.checked?'mesh':'stress';drawKey='';queue();}});
  function camera(value){lastCamera=value;Plotly.relayout(plot,{'scene.camera':value});}
  document.querySelector('#solidIso').onclick=()=>camera(initialCamera());
  document.querySelector('#solidTop').onclick=()=>camera({eye:{x:0,y:0,z:2.1},up:{x:0,y:1,z:0}});
  document.querySelector('#solidAlongX').onclick=()=>camera({eye:{x:2.1,y:0,z:0},up:{x:0,y:0,z:1}});
  document.querySelector('#solidAlongY').onclick=()=>camera({eye:{x:0,y:2.1,z:0},up:{x:0,y:0,z:1}});
  const oldDraw=draw,oldLocal=drawLocal;
  draw=()=>{if(displayMode==='local'&&localResult?.kind==='standaloneIntegralHub'&&document.body.dataset.module==='local'){show(localResult);return;}hide();oldDraw();};
  drawLocal=()=>{if(localResult?.kind==='standaloneIntegralHub'){show(localResult);return;}hide();oldLocal();};
  window.addEventListener('framecae-module-change',()=>{if(document.body.dataset.module!=='local')hide();else if(localResult?.kind==='standaloneIntegralHub'&&displayMode==='local')show(localResult);});
  window.FrameCAESolidView={show,hide,refresh:queue,export:()=>Plotly.downloadImage(plot,{format:'png',filename:'FrameCAE_N'+shown.node+'_XYZ应力云图',width:1500,height:1100})};
})();
