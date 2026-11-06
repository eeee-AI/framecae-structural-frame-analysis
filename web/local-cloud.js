(() => {
  // 局部云图直接绘制求解所用 Hex8 网格的真实边界三角面。不能再由每根
  // 独立圆管重建一层“漂亮外皮”：在马鞍口处那样的外皮没有布尔裁切关系，
  // 会把主管壁误画成洞，或产生互相穿透的表面。
  const previousDrawLocal = drawLocal;
  const actualHexBoundarySkin = mesh => ({
    nodes: mesh.nodes || [], faces: mesh.faces || [], values: mesh.faceVonMises || [],
    weldFaces: new Set(mesh.weldFaces || []),
  });

  const drawOuterSkin = (skin) => {
    setup();
    const width = canvas.clientWidth, height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);
    // The legacy A solver returns a rotated local mesh. B already uses axes
    // parallel to global XYZ; only the origin is translated to the frame node.
    const axes=localResult.coordinateFrame?.globalToLocal;
    const globalVector=point=>axes?[0,1,2].map(i=>axes.reduce((sum,row,j)=>sum+row[i]*point[j],0)):point;
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    skin.nodes.forEach(point => globalVector(point).forEach((value, index) => { low[index] = Math.min(low[index], value); high[index] = Math.max(high[index], value); }));
    const center = low.map((value, index) => (value + high[index]) / 2);
    const span = Math.max(...high.map((value, index) => value - low[index]), 1e-9);
    const pixels = Math.min(width, height) * .56 / span * view.zoom;
    const project = point => {
      point=globalVector(point);
      let x = point[0] - center[0], y = point[1] - center[1], z = point[2] - center[2];
      const p = window.FrameCAEModelView.projectOffset([x,y,z],view);
      return {x: width / 2 + p.x * pixels, y: height / 2 + p.y * pixels, depth: p.depth};
    };
    // Avoid spreading large surface arrays into function arguments, and project
    // each vertex once instead of repeatedly inside the sort comparator.
    const maximum = skin.values.reduce((peak, value) => Math.max(peak, value), 1e-18);
    const projected = skin.nodes.map(project);
    const color = value => `hsl(${260 - 260 * Math.min(1, value / maximum)},88%,48%)`;
    skin.faces.map((face, index) => ({face, value: skin.values[index], weld: skin.weldFaces.has(index), depth: face.reduce((sum,id)=>sum+projected[id].depth,0)})).sort((first, second) => first.depth-second.depth).forEach(item => {
      const points = item.face.map(id => projected[id]);
      ctx.globalAlpha = 1; ctx.fillStyle = color(item.value); ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y); ctx.lineTo(points[1].x, points[1].y); ctx.lineTo(points[2].x, points[2].y); ctx.closePath(); ctx.fill();
      const highlight = item.weld && document.querySelector('#genericShowWeld')?.checked;
      if (highlight || window.frameCAELocalCloudOptions?.meshEdges) {
        ctx.globalAlpha = highlight ? .65 : .18; ctx.strokeStyle = highlight ? '#343f4d' : '#1d2939'; ctx.lineWidth = highlight ? .8 : .4; ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    document.querySelector('#legendText').textContent = localResult?.kind==='abaqusIntegralHub'?'真实 C3D10 曲面边界 von Mises 应力':'真实 Hex8 外露边界 von Mises 应力';
    // Plot title lives in the shared result toolbar.
    return project;
  };

  const drawCutBoundaryMarkers = (project, arms) => {
    // 局部实体并非整根杆件，而是在节点附近截取的子模型。每根管的远端
    // 是向整体梁模型施加位移/转角的人工截断面；空心圆管在这里显示环形
    // 断面是正确的，不能用端盖封死。
    ctx.save();
    ctx.font = '12px sans-serif';
    const identity = window.FrameCAEModelView.describeNode(payload(), localResult.node);
    arms.forEach(arm => {
      const end = arm.direction.map(value => value * arm.length);
      const point = project(end);
      ctx.setLineDash([4, 3]); ctx.strokeStyle = '#a8571c'; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(point.x, point.y, 10, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = '#7c3e13';
      const member = identity?.arms.find(item => item.element === arm.element);
      const label = `E${arm.element}${member ? ' · 朝 N'+member.neighbor : ''}（截断面）`;
      const labelWidth = ctx.measureText(label).width;
      ctx.fillText(label, Math.max(8,Math.min(point.x+12,canvas.clientWidth-labelWidth-8)), Math.max(22,point.y-10));
    });
    if(identity){
      const p=project([0,0,0]);
      ctx.fillStyle='#fff';ctx.strokeStyle='#334e70';ctx.lineWidth=1.5;
      ctx.beginPath();ctx.arc(p.x,p.y,4,0,2*Math.PI);ctx.fill();ctx.stroke();
      ctx.font='bold 13px sans-serif';
      const label='整体节点 '+identity.label, labelWidth=ctx.measureText(label).width;
      const x=Math.max(8,Math.min(p.x+9,canvas.clientWidth-labelWidth-12)),y=Math.max(24,p.y+19);
      ctx.fillStyle='#fffffff0';ctx.fillRect(x-4,y-14,labelWidth+8,20);
      ctx.fillStyle='#203d61';ctx.fillText(label,x,y);
    }
    ctx.restore();
  };

  drawLocal = function () {
    if (!localResult?.tubeArms?.length || !localResult?.mesh?.nodalVonMises?.length) { previousDrawLocal(); return; }
    if (!localResult.actualHexBoundary) localResult.actualHexBoundary = actualHexBoundarySkin(localResult.mesh);
    const project = drawOuterSkin(localResult.actualHexBoundary);
    drawCutBoundaryMarkers(project, localResult.tubeArms);
    if (window.frameCAELocalCloudOptions?.peakMarker && localResult.result?.maximumNodalLocation) {
      const p=project(localResult.result.maximumNodalLocation);
      ctx.save();ctx.strokeStyle='#a32d50';ctx.fillStyle='#fff';ctx.lineWidth=2;
      ctx.beginPath();ctx.arc(p.x,p.y,6,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.fillStyle='#9b2e4c';ctx.font='12px sans-serif';
      ctx.fillText('节点平滑峰值',Math.max(5,Math.min(p.x+10,canvas.clientWidth-100)),Math.max(35,p.y-10));ctx.restore();
    }
    const toes=localResult.toePaths||localResult.verificationStudy?.toes;
    if(window.frameCAELocalCloudOptions?.peakMarker&&toes){
      const peak=Object.values(toes).filter(v=>v.peakPoint&&Number.isFinite(v.peakMises)).sort((a,b)=>b.peakMises-a.peakMises)[0];
      if(peak){
        const p=project(peak.peakPoint),label=`焊趾外推峰值 ${(peak.peakMises/1e6).toPrecision(5)} MPa`;
        ctx.save();ctx.strokeStyle='#6c246d';ctx.fillStyle='#fff';ctx.lineWidth=2;
        ctx.beginPath();ctx.arc(p.x,p.y,6,0,2*Math.PI);ctx.fill();ctx.stroke();ctx.font='12px sans-serif';
        const width=ctx.measureText(label).width,x=Math.max(8,Math.min(p.x+10,canvas.clientWidth-width-10)),y=Math.max(30,p.y-15);
        ctx.fillStyle='#fffffff0';ctx.fillRect(x-3,y-13,width+6,19);ctx.fillStyle='#6c246d';ctx.fillText(label,x,y);ctx.restore();
      }
    }
  };
  const previousWriteLocal = writeLocalResults;
  writeLocalResults = function () {
    previousWriteLocal();
    document.querySelector('#results').textContent = document.querySelector('#results').textContent.replace(/\n云图以闭合圆管显示[^\n]*/g, '');
    document.querySelector('#results').textContent += '\n云图直接绘制实际 Hex8 的外露边界三角面；颜色为该边界面节点 von Mises 应力均值。橙色虚线圈为局部子模型截断边界，不是节点开孔。';
  };
})();
