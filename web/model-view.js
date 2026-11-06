/* Structural identities and the global XYZ projection shared by every module. */
(() => {
  const nodeLabel = id => `N${Number(id)}`;
  const elementLabel = id => `E${Number(id)}`;
  function projectOffset(point, camera) {
    const [x, y, z] = point, cy = Math.cos(camera.yaw), sy = Math.sin(camera.yaw);
    const cp = Math.cos(camera.pitch), sp = Math.sin(camera.pitch);
    const horizontal = cy*x-sy*y, horizontalDepth = sy*x+cy*y;
    return {x: horizontal, y: sp*horizontalDepth-cp*z, depth: sp*z+cp*horizontalDepth};
  }
  function describeNode(model, id) {
    id = Number(id);
    const node = model.nodes?.find(n => Number(n.id) === id);
    if (!node) return null;
    return {id, label: nodeLabel(id), coordinate: ['x','y','z'].map(k => Number(node[k])),
      arms: (model.elements || []).filter(e => Number(e.start) === id || Number(e.end) === id)
        .map(e => ({element: Number(e.id), neighbor: Number(Number(e.start) === id ? e.end : e.start)}))};
  }
  function renameNode(model, previous, next) {
    previous = Number(previous); next = Number(next);
    if (!Number.isSafeInteger(next) || next < 1) throw Error('节点号必须为正整数。');
    const row = model.nodes.find(n => Number(n.id) === previous);
    if (!row) throw Error('待修改节点不存在。');
    if (model.nodes.some(n => Number(n.id) === next && n !== row)) throw Error(`${nodeLabel(next)} 已存在，请使用其他节点号。`);
    row.id = next;
    (model.elements || []).forEach(e => { if (Number(e.start) === previous) e.start = next; if (Number(e.end) === previous) e.end = next; });
    for (const key of ['loads','constraints']) (model[key] || []).forEach(r => { if (Number(r.node) === previous) r.node = next; });
  }
  function drawAxes(context, width, height, camera) {
    if (width < 160 || height < 130) return;
    const origin = {x: 73, y: height-63}, length = 43;
    context.save();context.setLineDash([]);context.globalAlpha=1;
    context.fillStyle='#fffffff0';context.fillRect(9,height-133,143,122);
    context.font='11px sans-serif';context.fillStyle='#52657b';context.fillText('全局 XYZ',18,height-114);
    [[1,0,0,'X','#d33c4a'],[0,1,0,'Y','#1b9b61'],[0,0,1,'Z','#2871cf']].map(([x,y,z,label,color]) =>
      ({...projectOffset([x,y,z],camera),label,color})).sort((a,b)=>a.depth-b.depth).forEach(axis => {
        const end={x:origin.x+axis.x*length,y:origin.y+axis.y*length};
        context.strokeStyle=context.fillStyle=axis.color;context.lineWidth=2;
        context.beginPath();context.moveTo(origin.x,origin.y);context.lineTo(end.x,end.y);context.stroke();
        const magnitude=Math.hypot(axis.x,axis.y);
        if(magnitude>.08){const ux=axis.x/magnitude,uy=axis.y/magnitude;context.beginPath();context.moveTo(end.x,end.y);context.lineTo(end.x-7*ux+3*uy,end.y-7*uy-3*ux);context.lineTo(end.x-7*ux-3*uy,end.y-7*uy+3*ux);context.closePath();context.fill();}
        else{context.beginPath();context.arc(end.x,end.y,3,0,2*Math.PI);context.stroke();}
        context.font='bold 12px sans-serif';context.fillText('+'+axis.label,end.x+4,end.y-5);
      });
    context.restore();
  }
  function localProblemMatches(saved,current) {
    if((saved.couplingMode||'forceSubmodel')!==(current.couplingMode||'forceSubmodel'))return false;
    if(current.couplingMode==='forceSubmodel'&&(saved.shearDistribution||'resultantAffine')!==(current.shearDistribution||'resultantAffine'))return false;
    function close(a,b,path) {
      if(typeof a==='number'&&typeof b==='number'){
        if(path==='node'||path.endsWith('.element'))return a===b;
        const absolute=/beamCutWrench|beamSection/.test(path)?1e-6:path.endsWith('.nominalStress')?1e-3:1e-12;
        return Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=absolute+1e-11*Math.max(Math.abs(a),Math.abs(b));
      }
      if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((v,i)=>close(v,b[i],path+'['+i+']'));
      if(a&&b&&typeof a==='object'&&typeof b==='object'){
        const keys=Object.keys(a).sort(),other=Object.keys(b).sort();
        return JSON.stringify(keys)===JSON.stringify(other)&&keys.every(k=>close(a[k],b[k],path+'.'+k));
      }
      return a===b;
    }
    return ['node','origin','geometry','arms','mesh','material','load','gravity','memberLoadMapping'].every(k=>close(saved[k],current[k],k));
  }
  // Loads are summed in global coordinates, matching the solver's axes.
  function collectDisplayLoads(model) {
    const valid=v=>Number.isFinite(Number(v))?Number(v):0;
    const nodes=new Map((model.nodes||[]).map(n=>[Number(n.id),n]));
    const elements=new Map((model.elements||[]).map(e=>[Number(e.id),e]));
    const nodal=new Map(),uniform=new Map();
    const add=(map,id,v)=>{const old=map.get(id)||[0,0,0];map.set(id,old.map((x,i)=>x+v[i]));};
    for(const l of model.loads||[])if(nodes.has(Number(l.node)))add(nodal,Number(l.node),['fx','fy','fz'].map(k=>valid(l[k])));
    for(const l of model.memberLoads||[]) {
      if(String(l.type).toLowerCase()!=='uniform')continue;
      const id=Number(l.element),e=elements.get(id),a=nodes.get(Number(e?.start)),b=nodes.get(Number(e?.end));if(!a||!b)continue;
      let v=['qx','qy','qz'].map(k=>valid(l[k]));
      if(String(l.coordinateSystem||'local').toLowerCase()==='local') {
        const chord=['x','y','z'].map(k=>Number(b[k])-Number(a[k])),len=Math.hypot(...chord);if(len<=1e-10)continue;
        const ex=chord.map(x=>x/len),ref=Math.abs(ex[2])>1-1e-10?[0,1,0]:[0,0,1];
        const dot=ref.reduce((s,x,i)=>s+x*ex[i],0),ey0=ref.map((x,i)=>x-dot*ex[i]),norm=Math.hypot(...ey0),ey=ey0.map(x=>x/norm);
        const ez=[ex[1]*ey[2]-ex[2]*ey[1],ex[2]*ey[0]-ex[0]*ey[2],ex[0]*ey[1]-ex[1]*ey[0]];
        v=ex.map((x,i)=>v[0]*x+v[1]*ey[i]+v[2]*ez[i]);
      }
      add(uniform,id,v);
    }
    return {nodal:[...nodal].filter(([,v])=>Math.hypot(...v)>1e-12).map(([id,vector])=>({id,point:nodes.get(id),vector,magnitude:Math.hypot(...vector)})),
      uniform:[...uniform].filter(([,v])=>Math.hypot(...v)>1e-12).map(([id,vector])=>({id,start:nodes.get(Number(elements.get(id).start)),end:nodes.get(Number(elements.get(id).end)),vector,magnitude:Math.hypot(...vector)}))};
  }
  function loadGlyphSize(value,maximum,distributed=false) {
    const ratio=maximum>0?Math.sqrt(Math.max(0,Math.min(1,value/maximum))):0;
    return {length:(distributed?20:30)+(distributed?36:62)*ratio,width:(distributed?1.1:1.5)+(distributed?1.3:2.7)*ratio};
  }
  function drawModelLoads(ctx,model,project,width,height,options={}) {
    const loads=collectDisplayLoads(model);if(!loads.nodal.length&&!loads.uniform.length)return;
    const fmt=(v,q)=>`${Number((v>=1000?v/1000:v).toPrecision(3))} ${v>=1000?'kN':'N'}${q?'/m':''}`;
    const labels=[];
    const tag=(text,p,color)=>{ctx.font='600 11px "Segoe UI",sans-serif';const w=ctx.measureText(text).width+12,h=21;let x=Math.max(6,Math.min(width-w-6,p.x-(p.align==='right'?w:p.align==='center'?w/2:0))),y=Math.max(31,Math.min(height-h-30,p.y));for(let i=0;i<6&&labels.some(r=>x<r.x+r.w&&x+w>r.x&&y<r.y+r.h&&y+h>r.y);i++)y=Math.max(31,y-h-3);labels.push({x,y,w,h});ctx.fillStyle='#fffdf7ee';ctx.fillRect(x,y,w,h);ctx.strokeStyle=color;ctx.lineWidth=.7;ctx.strokeRect(x,y,w,h);ctx.fillStyle=color;ctx.fillText(text,x+6,y+14);};
    const arrow=(p,vector,size,color,gap)=>{
      const tip=project(p),m=Math.hypot(...vector),u=vector.map(v=>v/m),ahead=project({x:p.x+u[0],y:p.y+u[1],z:p.z+u[2]});
      const dx=ahead.x-tip.x,dy=ahead.y-tip.y,l=Math.hypot(dx,dy),depth=ahead.depth-tip.depth;
      ctx.strokeStyle=ctx.fillStyle=color;ctx.lineWidth=size.width;ctx.lineCap='round';
      // Near view-normal force: dot (toward viewer) or cross (away), never invent a direction.
      const unit0=project({x:0,y:0,z:0}),unitAxes=[{x:1,y:0,z:0},{x:0,y:1,z:0},{x:0,y:0,z:1}].map(project);
      const pixels=Math.sqrt(unitAxes.reduce((s,a)=>s+(a.x-unit0.x)**2+(a.y-unit0.y)**2,0)/2);
      if(l<Math.max(1e-9,pixels*.06)){
        const r=5+size.width;ctx.beginPath();ctx.arc(tip.x,tip.y,r,0,2*Math.PI);ctx.stroke();
        ctx.beginPath();if(depth>=0){ctx.arc(tip.x,tip.y,2.2,0,2*Math.PI);ctx.fill();}else{ctx.moveTo(tip.x-r*.5,tip.y-r*.5);ctx.lineTo(tip.x+r*.5,tip.y+r*.5);ctx.moveTo(tip.x+r*.5,tip.y-r*.5);ctx.lineTo(tip.x-r*.5,tip.y+r*.5);ctx.stroke();}
        return {x:tip.x,y:tip.y-15,normal:true};
      }
      const ux=dx/l,uy=dy/l,foreshorten=Math.min(1,l/Math.max(pixels,1e-9)),len=Math.max(12,size.length*foreshorten);
      const head={x:tip.x-ux*gap,y:tip.y-uy*gap},tail={x:head.x-ux*len,y:head.y-uy*len},h=Math.min(len*.45,7+size.width*1.3),half=h*.43;
      ctx.beginPath();ctx.moveTo(tail.x,tail.y);ctx.lineTo(head.x-ux*h*.65,head.y-uy*h*.65);ctx.stroke();
      ctx.beginPath();ctx.moveTo(head.x,head.y);ctx.lineTo(head.x-ux*h+uy*half,head.y-uy*h-ux*half);ctx.lineTo(head.x-ux*h-uy*half,head.y-uy*h+ux*half);ctx.closePath();ctx.fill();
      return tail;
    };
    ctx.save();
    const maxQ=Math.max(0,...loads.uniform.map(l=>l.magnitude));
    for(const q of loads.uniform){
      const a=project(q.start),b=project(q.end),span=Math.hypot(b.x-a.x,b.y-a.y),count=Math.max(3,Math.min(11,Math.round(span/38)+1)),size=loadGlyphSize(q.magnitude,maxQ,true);
      const v=project({x:q.start.x+q.vector[0]/q.magnitude,y:q.start.y+q.vector[1]/q.magnitude,z:q.start.z+q.vector[2]/q.magnitude});
      const dl=Math.hypot(v.x-a.x,v.y-a.y);if(span>0&&dl>0&&Math.abs(((b.x-a.x)*(v.x-a.x)+(b.y-a.y)*(v.y-a.y))/(span*dl))>.88)size.length=Math.min(size.length,Math.max(14,span/(count-1)*.7));
      const tails=[];for(let i=0;i<count;i++){const t=.07+.86*i/(count-1),p={x:Number(q.start.x)+(q.end.x-q.start.x)*t,y:Number(q.start.y)+(q.end.y-q.start.y)*t,z:Number(q.start.z)+(q.end.z-q.start.z)*t};tails.push(arrow(options.memberPoint?.(q,t,p)||p,q.vector,size,'#8543b1',4));}
      if(!tails.some(t=>t.normal)){ctx.strokeStyle='#8543b1';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(tails[0].x,tails[0].y);tails.slice(1).forEach(t=>ctx.lineTo(t.x,t.y));ctx.stroke();}
      const mid=tails[Math.floor(tails.length/2)];tag(`E${q.id} · q = ${fmt(q.magnitude,true)}`,{x:mid.x,y:Math.min(...tails.map(t=>t.y))-27,align:'center'},'#75359d');
    }
    const maxF=Math.max(0,...loads.nodal.map(l=>l.magnitude));
    for(const f of loads.nodal){const p={x:Number(f.point.x),y:Number(f.point.y),z:Number(f.point.z)},tail=arrow(options.nodePoint?.(f,p)||p,f.vector,loadGlyphSize(f.magnitude,maxF),'#cf3549',9);tag(`N${f.id} · F = ${fmt(f.magnitude,false)}`,{x:tail.x-8,y:tail.y-25,align:'right'},'#b32239');}
    if(options.legend!==false){ctx.font='11px "Microsoft YaHei",sans-serif';ctx.fillStyle='#fffdf7e8';ctx.fillRect(7,height-25,Math.min(width-14,470),21);ctx.fillStyle='#5d536b';ctx.fillText('红：节点合力  紫：均布合力 ｜ 大小为相对示意，数值以标注为准',13,height-11);}ctx.restore();
  }


  // Plotly uses world coordinates; the input remains the immutable solved model.
  function loadTraces(model, span, labelSuffix='') {
    const loads=collectDisplayLoads(model),traces=[];
    const xyz=p=>[Number(p.x),Number(p.y),Number(p.z)];
    const fmt=(v,q)=>`${Number((v>=1000?v/1000:v).toPrecision(3))} ${v>=1000?'kN':'N'}${q?'/m':''}`;
    for(const [items,isQ,color] of [[loads.uniform,true,'#8543b1'],[loads.nodal,false,'#cf3549']]) {
      const maximum=Math.max(0,...items.map(l=>l.magnitude));
      for(const l of items) {
        const size=loadGlyphSize(l.magnitude,maximum,isQ),length=span*size.length/650;
        const unit=l.vector.map(v=>v/l.magnitude),tips=[],tails=[],x=[],y=[],z=[];
        const points=isQ?Array.from({length:7},(_,i)=>xyz(l.start).map((v,k)=>v+(.07+.86*i/6)*(xyz(l.end)[k]-v))):[xyz(l.point)];
        for(const p of points){const tip=p.map((v,k)=>v-unit[k]*span*.004),tail=tip.map((v,k)=>v-unit[k]*length);tips.push(tip);tails.push(tail);for(const v of [tail,tip]){x.push(v[0]);y.push(v[1]);z.push(v[2]);}x.push(null);y.push(null);z.push(null);}
        const text=`${isQ?'E':'N'}${l.id} · ${isQ?'q':'F'} = ${fmt(l.magnitude,isQ)}${isQ?labelSuffix:''}`;
        traces.push({type:'scatter3d',mode:'lines',x,y,z,line:{color,width:size.width+1},name:text,hovertemplate:text+'<extra></extra>',showlegend:false});
        traces.push({type:'cone',x:tips.map(p=>p[0]),y:tips.map(p=>p[1]),z:tips.map(p=>p[2]),u:tips.map(()=>unit[0]),v:tips.map(()=>unit[1]),w:tips.map(()=>unit[2]),anchor:'tip',sizemode:'absolute',sizeref:length*.24,colorscale:[[0,color],[1,color]],showscale:false,hoverinfo:'skip',showlegend:false});
        if(isQ)traces.push({type:'scatter3d',mode:'lines',x:tails.map(p=>p[0]),y:tails.map(p=>p[1]),z:tails.map(p=>p[2]),line:{color,width:2},hoverinfo:'skip',showlegend:false});
        const p=tails[Math.floor(tails.length/2)];traces.push({type:'scatter3d',mode:'text',x:[p[0]],y:[p[1]],z:[p[2]],text:[text],textposition:'top center',textfont:{color,size:12},hoverinfo:'skip',showlegend:false});
      }
    }
    return traces;
  }
  function localLoadModel(answer) {
    const q=answer.resolvedLocalRequest||answer.localRequest,origin=answer.origin;
    const nodes=[{id:0,x:origin[0],y:origin[1],z:origin[2]}],elements=[],memberLoads=[];
    for(const [i,a] of q.arms.entries()){
      const p=a.direction.map((v,k)=>origin[k]+v*a.length);nodes.push({id:i+1,x:p[0],y:p[1],z:p[2]});
      elements.push({id:a.element,start:0,end:i+1});
      const row=q.memberLoadMapping?.loads?.find(l=>l.element===a.element),v=row?.globalQ;
      if(v)memberLoads.push({element:a.element,type:'uniform',coordinateSystem:'global',qx:v[0],qy:v[1],qz:v[2]});
    }
    const f=q.load?.wrench||[];
    return {nodes,elements,memberLoads,loads:[{node:0,fx:f[0]||0,fy:f[1]||0,fz:f[2]||0}]};
  }

  const api={loadTraces,localLoadModel,collectDisplayLoads,loadGlyphSize,drawModelLoads,nodeLabel,elementLabel,projectOffset,describeNode,renameNode,drawAxes,localProblemMatches};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof window!=='undefined')window.FrameCAEModelView=api;
})();
