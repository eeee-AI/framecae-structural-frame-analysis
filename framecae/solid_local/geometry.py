"""Native OpenCASCADE geometry and boundary-fitted quadratic Gmsh mesh."""
import json,math,time
from pathlib import Path
import numpy as np
import gmsh

EDGES=((0,1),(1,2),(0,2),(0,3),(1,3),(2,3))


def native_permutation(element_type,expected):
    props=gmsh.model.mesh.getElementProperties(element_type)
    local=np.asarray(props[4]).reshape(props[3],props[1])
    ids=[int(np.argmin(np.linalg.norm(local-np.asarray(p),axis=1))) for p in expected]
    if len(set(ids))!=len(ids):raise ValueError('Invalid Gmsh element node order')
    return ids


def build(request,directory,toe_size,body_size=.025,focus_size=.010):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    started=time.time();gmsh.initialize();gmsh.option.setNumber('General.Terminal',1)
    gmsh.option.setNumber('General.NumThreads',1);gmsh.option.setNumber('Mesh.RandomSeed',1)
    gmsh.option.setNumber('Mesh.HighOrderOptimize',0);gmsh.option.setNumber('Mesh.ElementOrder',1)
    gmsh.model.add('N%d_integral_hub'%request['node'])
    occ=gmsh.model.occ;g=request['geometry'];r=request['arms'][0]['outerRadius'];ri=request['arms'][0]['innerRadius'];hub=g['hubRadius']
    try:
        print('CAD_BEGIN',flush=True)
        outer=occ.addSphere(0,0,0,hub);arms=[]
        def orient(vol,d):
            z=np.array([0.,0.,1.]);d=np.asarray(d);axis=np.cross(z,d);cs=float(z@d)
            if np.linalg.norm(axis)>1e-12:occ.rotate([(3,vol)],0,0,0,*axis,math.acos(np.clip(cs,-1,1)))
            elif cs<0:occ.rotate([(3,vol)],0,0,0,1,0,0,math.pi)
        cut_surfaces={}
        for arm in request['arms']:
            r=arm['outerRadius']
            center=g['weldDistance'];width=g['weldWidth'];height=g['reinforcement'];toe=g['toeRadius']
            left=center-width/2;right=center+width/2;crown=(width*width/4+height*height)/(2*height)-toe
            c1=np.array([r+toe,left]);c2=np.array([r+height-crown,center]);c3=np.array([r+toe,right])
            touch=c1+toe/(toe+crown)*(c2-c1);touch2=np.array([touch[0],2*center-touch[1]])
            f=g['blendWidth'];rc=r+f;sc=math.sqrt((hub+f)**2-rc**2);rs=hub/(hub+f)*rc;ss=hub/(hub+f)*sc
            # The buried first segment lies wholly inside the sphere. The
            # exposed shoulder is one exact tangent circular arc, not OCC's
            # tolerance-heavy multi-surface automatic B-spline fillet.
            coords=[(.95*rs,ss-.5*f),(rs,ss),(r,sc),(r,left),touch,touch2,(r,right),(r,arm['length']),(0,arm['length']),(0,ss-.5*f)]
            pts=[occ.addPoint(float(p[0]),0,float(p[1])) for p in coords]
            centers=[occ.addPoint(float(p[0]),0,float(p[1])) for p in [c1,c2,c3]]
            shoulder_center=occ.addPoint(rc,0,sc)
            curves=[occ.addLine(pts[0],pts[1]),occ.addCircleArc(pts[1],shoulder_center,pts[2]),occ.addLine(pts[2],pts[3]),
                    occ.addCircleArc(pts[3],centers[0],pts[4]),occ.addCircleArc(pts[4],centers[1],pts[5]),occ.addCircleArc(pts[5],centers[2],pts[6])]
            curves.extend(occ.addLine(pts[i],pts[(i+1)%len(pts)]) for i in range(6,len(pts)))
            face=occ.addPlaneSurface([occ.addCurveLoop(curves)])
            rev=occ.revolve([(2,face)],0,0,0,0,0,1,2*math.pi)
            vol=next(tag for dim,tag in rev if dim==3);orient(vol,arm['direction']);arms.append((3,vol))
        fused,_=occ.fuse([(3,outer)],arms);occ.synchronize()
        print('CAD_OUTER_FUSED',flush=True)
        volumes=[tag for dim,tag in fused if dim==3]
        if len(volumes)!=1:raise ValueError('Outer geometry did not fuse into one volume')
        filleted=fused
        print('CAD_ANALYTIC_SHOULDERS',flush=True)
        cutters=[]
        for arm in request['arms']:
            ri=arm['innerRadius']
            # One revolved hemisphere + cylinder avoids a tangent sphere/cylinder
            # boolean with ambiguous OCC face orientation. Same physical bore.
            b=g['boreStart']+ri;end=arm['length']+.03
            tip=occ.addPoint(0,0,b-ri);eq=occ.addPoint(ri,0,b);up=occ.addPoint(ri,0,end);axis_up=occ.addPoint(0,0,end);center=occ.addPoint(0,0,b)
            arcs=[occ.addCircleArc(tip,center,eq),occ.addLine(eq,up),occ.addLine(up,axis_up),occ.addLine(axis_up,tip)]
            face=occ.addPlaneSurface([occ.addCurveLoop(arcs)]);rev=occ.revolve([(2,face)],0,0,0,0,0,1,2*math.pi)
            vol=next(tag for dim,tag in rev if dim==3);orient(vol,arm['direction']);cutters.append((3,vol))
        solid,_=occ.cut(filleted,cutters);occ.synchronize()
        print('CAD_BORES_CUT',flush=True)
        volumes=[tag for dim,tag in solid if dim==3]
        if len(volumes)!=1:raise ValueError('Final solid must be one connected CAD volume')
        occ.removeAllDuplicates();occ.synchronize()
        # Full revolutions leave the original 2D sketch faces/arc centres in OCC.
        # Meshing those unrelated faces can reclassify shared high-order nodes
        # onto the sketch curves. Keep only the final solid and its topology.
        keep={(3,volumes[0])};front=[(3,volumes[0])]
        for dim in (2,1,0):
            front=gmsh.model.getBoundary(front,combined=False,oriented=False)
            front=list(set((d,abs(t)) for d,t in front));keep.update(front)
        removed=[]
        for dim in (2,1,0):
            extra=[ent for ent in gmsh.model.getEntities(dim) if ent not in keep]
            if extra:occ.remove(extra,recursive=False);occ.synchronize();removed.extend(extra)
        print('REMOVED_CONSTRUCTION_ENTITIES',len(removed),flush=True)
        surfaces=gmsh.model.getBoundary([(3,volumes[0])],oriented=False)
        curves=sorted({tag for dim,tag in gmsh.model.getBoundary(surfaces,combined=False,oriented=False) if dim==1})
        from .curved_mesh import audit_endpoints
        topology_audit=audit_endpoints(curves);print('CAD_TOPOLOGY_AUDIT',topology_audit,flush=True)
        toe_curves=[];seam_curves=[];focus_curves=[]
        for tag in curves:
            low,high=gmsh.model.getParametrizationBounds(1,tag);u=np.linspace(low[0],high[0],5)
            p=np.asarray(gmsh.model.getValue(1,tag,u)).reshape(-1,3)
            if np.linalg.norm(p.mean(axis=0))<hub+.04:focus_curves.append(tag)
            for arm in request['arms']:
                axial=p@np.asarray(arm['direction']);radial=np.linalg.norm(p-axial[:,None]*np.asarray(arm['direction']),axis=1)
                if np.max(np.abs(axial-g['weldDistance']))<g['weldWidth']*.7 and np.min(radial)>arm['outerRadius']*.95:
                    seam_curves.append(tag)
                    if np.ptp(axial)<1e-7 and (abs(axial.mean()-(g['weldDistance']-g['weldWidth']/2))<1e-6 or abs(axial.mean()-(g['weldDistance']+g['weldWidth']/2))<1e-6):toe_curves.append(tag)
        toe_curves=sorted(set(toe_curves));seam_curves=sorted(set(seam_curves));focus_curves=sorted(set(focus_curves))
        expected_toes=2*len(request['arms'])
        if len(toe_curves)<expected_toes:raise ValueError('Missing circular toe rings: expected at least '+str(expected_toes)+', got '+str(len(toe_curves)))
        # Explicit curve counts keep all circumference edges adequately resolved.
        for tag in curves:
            size=toe_size if tag in toe_curves else focus_size if tag in focus_curves or tag in seam_curves else body_size
            n=max(3,int(math.ceil(occ.getMass(1,tag)/size))+1)
            gmsh.model.mesh.setTransfiniteCurve(tag,n)
        fields=[]
        for tags,size,near,far in [(toe_curves,toe_size,min(toe_size,.001),.006),(focus_curves,focus_size,.006,.035)]:
            dist=gmsh.model.mesh.field.add('Distance');gmsh.model.mesh.field.setNumbers(dist,'CurvesList',tags);gmsh.model.mesh.field.setNumber(dist,'Sampling',160)
            threshold=gmsh.model.mesh.field.add('Threshold')
            for key,value in [('InField',dist),('SizeMin',size),('SizeMax',body_size),('DistMin',near),('DistMax',far)]:gmsh.model.mesh.field.setNumber(threshold,key,value)
            fields.append(threshold)
        combined=gmsh.model.mesh.field.add('Min');gmsh.model.mesh.field.setNumbers(combined,'FieldsList',fields);gmsh.model.mesh.field.setAsBackgroundMesh(combined)
        gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0);gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',0);gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
        gmsh.option.setNumber('Mesh.MeshSizeMin',min(toe_size,focus_size));gmsh.option.setNumber('Mesh.MeshSizeMax',body_size)
        gmsh.option.setNumber('Mesh.Algorithm3D',request['mesh'].get('algorithm3D',1));gmsh.option.setNumber('Mesh.Optimize',1)
        gmsh.model.addPhysicalGroup(3,volumes,name='SOLID')
        for arm in request['arms']:
            cut=[];d=np.asarray(arm['direction'])
            for dim,tag in surfaces:
                if gmsh.model.getType(2,tag)=='Plane' and abs(np.asarray(occ.getCenterOfMass(2,tag))@d-arm['length'])<1e-7:cut.append(tag)
            if len(cut)!=1:raise ValueError('Expected one annular CAD end face')
            gmsh.model.addPhysicalGroup(2,cut,name='CUT_E'+str(arm['element']))
            cut_surfaces[str(arm['element'])]=cut
        print('LINEAR_MESH_BEGIN',flush=True);gmsh.model.mesh.generate(3);print('LINEAR_MESH_DONE',flush=True)
        # The extra sub-millimetre case can expose slivers which invert after
        # curving. Improve the linear tetrahedra before moving their midsides.
        if request['mesh'].get('algorithm3D',1)!=10:gmsh.model.mesh.optimize('Netgen')
        gmsh.model.mesh.setOrder(2)
        from .curved_mesh import place_midsides
        projection=place_midsides();print('CAD_MIDSIDE_PROJECTION',projection,flush=True)
        gmsh.option.setNumber('General.NumThreads',1)
        # CAD-projected Tet10 is already curved. Avoid invoking the native
        # moving-barrier optimizer for valid positive-Jacobian meshes: it can
        # abort the process when an optional quality target is unattainable.
        types,labels0,_=gmsh.model.mesh.getElements(3)
        quality0=gmsh.model.mesh.getElementQualities(np.concatenate(labels0),'minDetJac')
        print('CURVED_INITIAL_QUALITY',len(quality0),int(np.count_nonzero(quality0<=0)),float(np.min(quality0)),flush=True)
        repaired=False
        if np.min(quality0)<=0:
            gmsh.write(str(directory/'preoptimization.msh'))
            # Save independent coordinate/Jacobian evidence before a native optimizer.
            ts,xyz,_=gmsh.model.mesh.getNodes();ix=np.argsort(ts);ts=np.asarray(ts)[ix];xyz=np.asarray(xyz).reshape(-1,3)[ix]
            types0,lab0,raw0=gmsh.model.mesh.getElements(3)
            refs0=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[.5,0,.5],[0,.5,.5]])
            cn=np.vstack([np.searchsorted(ts,np.asarray(v).reshape(-1,10)[:,native_permutation(t,refs0)]) for t,v in zip(types0,raw0)])
            np.savez_compressed(directory/'jacobian_debug.npz',points=xyz,tetra10=cn,gmsh_quality=quality0)
            detail=[]
            for ci in np.flatnonzero(quality0<=0)[:8]:
                row=cn[ci];crd=xyz[row];edge=[(0,1),(1,2),(0,2),(0,3),(1,3),(2,3)]
                j=max(range(6),key=lambda j:np.linalg.norm(crd[4+j]-(crd[edge[j][0]]+crd[edge[j][1]])/2));a,b=edge[j]
                nid=int(ts[row[j+4]]);val,param,dim,entity=gmsh.model.mesh.getNode(nid)
                native,_=gmsh.model.getClosestPoint(dim,entity,np.r_[crd[a],crd[b]])
                detail.append(dict(cell=int(ci),node=nid,owner=[dim,entity],entityType=gmsh.model.getType(dim,entity),corners=crd[[a,b]].tolist(),midpoint=crd[j+4].tolist(),projectedEndpoints=np.asarray(native).reshape(-1,3).tolist(),endpointOwners=[list(gmsh.model.mesh.getNode(int(ts[row[k]]))[2:]) for k in (a,b)]))
            (directory/'jacobian_entities.json').write_text(json.dumps(detail,indent=2),encoding='utf-8')
            raise ValueError('Invalid curved mesh; pre-optimization coordinates saved for independent diagnosis')
        gmsh.write(str(directory/'geometry.step'));gmsh.write(str(directory/'mesh.msh'))
        tags,coord,_=gmsh.model.mesh.getNodes();tags=np.asarray(tags,dtype=np.int64);coord=np.asarray(coord).reshape(-1,3)
        order=np.argsort(tags);tags=tags[order];coord=coord[order]
        etypes,element_tags,nodes=gmsh.model.mesh.getElements(3)
        expected=np.vstack((np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]]),np.array([(.5,.0,.0),(.5,.5,0),(0,.5,0),(0,0,.5),(.5,0,.5),(0,.5,.5)])))
        conns=[];labels=[]
        for typ,el,conn in zip(etypes,element_tags,nodes):
            if typ!=11:raise ValueError('Only quadratic tetrahedra supported')
            conn=np.asarray(conn).reshape(-1,10)[:,native_permutation(typ,expected)]
            conns.append(np.searchsorted(tags,conn));labels.extend(el)
        conn=np.vstack(conns).astype(np.int32)
        tri_expected=np.array([[0,0],[1,0],[0,1],[.5,0],[.5,.5],[0,.5]])
        tris=[];surface_ids=[]
        for dim,tag in surfaces:
            types,_,nodes=gmsh.model.mesh.getElements(2,tag)
            for typ,nd in zip(types,nodes):
                if typ!=9:raise ValueError('Only quadratic boundary triangles supported')
                a=np.asarray(nd).reshape(-1,6)[:,native_permutation(typ,tri_expected)]
                tris.append(np.searchsorted(tags,a));surface_ids.extend([tag]*len(a))
        tris=np.vstack(tris).astype(np.int32)
        cut_tags={key:np.unique(np.concatenate([gmsh.model.mesh.getNodes(2,tag,includeBoundary=True)[0] for tag in vals])) for key,vals in cut_surfaces.items()}
        used=np.unique(conn);remap=np.full(len(coord),-1,dtype=np.int32);remap[used]=np.arange(len(used),dtype=np.int32)
        cut_sets={key:remap[np.searchsorted(tags,vals)].astype(np.int32) for key,vals in cut_tags.items()}
        conn=remap[conn];tris=remap[tris];coord=coord[used]
        if np.any(tris<0):raise ValueError('Boundary node not connected to volume elements')
        volume=float(occ.getMass(3,volumes[0]));quality=gmsh.model.mesh.getElementQualities(labels,'minDetJac')
        meta={'nodes':len(coord),'elements':len(conn),'boundaryTriangles':len(tris),'elementType':'curved isoparametric Tet10',
              'canonicalEdges':EDGES,'nativeVolumes':len(volumes),'cadVolumeM3':volume,'shoulderRadiusM':g['blendWidth'],
              'toeRadiusM':g['toeRadius'],'toeRings':len(toe_curves),'seamCurves':len(seam_curves),
              'toeSize':toe_size,'bodySize':body_size,'focusSize':focus_size,'minGmshDetJac':float(np.min(quality)),
              'generationSeconds':time.time()-started,'gmshVersion':gmsh.__version__,
              'linearNetgenOptimization':request['mesh'].get('algorithm3D',1)!=10,'highOrderDirectRepair':repaired,
              'boundaryProjectionAudit':projection,
              'removedConstructionEntities':len(removed),
              'cadTopologyAudit':topology_audit,
              'cutSelection':'native CAD annular faces, including midside nodes'}
        if meta['minGmshDetJac']<=0:raise ValueError('Non-positive curved mesh Jacobian')
        np.savez_compressed(directory/'mesh.npz',points=coord,tetra10=conn,triangle6=tris,surface_ids=np.asarray(surface_ids,dtype=np.int32),**{'cut_E'+k:v for k,v in cut_sets.items()})
        (directory/'mesh_meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        return meta
    finally:gmsh.finalize()
