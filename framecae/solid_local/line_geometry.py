"""OCC hollow cylinders with curved Tet10 boundaries and explicit clamp set."""
import json,time,math
from pathlib import Path
import numpy as np
import gmsh
from .geometry import native_permutation,EDGES


def build(request,directory,toe_size=None,body_size=None,focus_size=None):
    directory=Path(directory);started=time.time();arms=request['arms'];g=request['geometry'];d=np.asarray(g['axis']);L=arms[0]['length']
    fixed=request['analysisType']=='idealClamp';start=np.zeros(3) if fixed else -L*d;length=L if fixed else 2*L
    ro,ri=arms[0]['outerRadius'],arms[0]['innerRadius'];body=request['mesh']['size'];fine=request['mesh']['toeSize'];focus=request['mesh']['focusSize']
    gmsh.initialize();occ=gmsh.model.occ
    try:
        gmsh.option.setNumber('General.NumThreads',1);gmsh.option.setNumber('Mesh.RandomSeed',1);gmsh.option.setNumber('Mesh.HighOrderOptimize',0)
        gmsh.model.add('continuous_hollow_pipe')
        outer=occ.addCylinder(*start,*(length*d),ro);inner=occ.addCylinder(*start,*(length*d),ri)
        vol,_=occ.cut([(3,outer)],[(3,inner)]);occ.synchronize();volumes=[v for dim,v in vol]
        surfaces=gmsh.model.getBoundary(vol,oriented=False);cuts={};clamp=[]
        from .curved_mesh import audit_endpoints
        topology_audit=audit_endpoints(sorted({tag for dim,tag in gmsh.model.getBoundary(surfaces,combined=False,oriented=False) if dim==1}))
        for arm in arms:
            a=np.asarray(arm['direction']);cuts[str(arm['element'])]=[tag for dim,tag in surfaces if gmsh.model.getType(2,tag)=='Plane' and abs(np.asarray(occ.getCenterOfMass(2,tag))@a-L)<1e-8]
            if len(cuts[str(arm['element'])])!=1:raise ValueError('Missing pipe annular cut')
            gmsh.model.addPhysicalGroup(2,cuts[str(arm['element'])],name='CUT_E'+str(arm['element']))
        if fixed:
            clamp=[tag for dim,tag in surfaces if gmsh.model.getType(2,tag)=='Plane' and abs(np.asarray(occ.getCenterOfMass(2,tag))@d)<1e-8]
            if len(clamp)!=1:raise ValueError('Missing ideal clamped annular face')
            gmsh.model.addPhysicalGroup(2,clamp,name='IDEAL_CLAMP')
        gmsh.model.addPhysicalGroup(3,volumes,name='SOLID')
        # Refine the clamp neighbourhood or the fixed physical loading strip.
        f=gmsh.model.mesh.field.add('MathEval');axis='('+'+'.join('(%g*%s)'%(value,name) for value,name in zip(d,'xyz'))+')'
        distance=axis if fixed else 'Fabs('+axis+')'
        gmsh.model.mesh.field.setString(f,'F',f'{fine}+({body}-{fine})*Min(1,Max(0,({distance}-0.065)/0.09))')
        gmsh.model.mesh.field.setAsBackgroundMesh(f)
        for key,value in [('Mesh.MeshSizeFromPoints',0),('Mesh.MeshSizeFromCurvature',0),('Mesh.MeshSizeExtendFromBoundary',0),('Mesh.MeshSizeMin',fine),('Mesh.MeshSizeMax',body),('Mesh.Algorithm3D',request['mesh'].get('algorithm3D',10))]:gmsh.option.setNumber(key,value)
        gmsh.model.mesh.generate(3)
        if request['mesh'].get('algorithm3D',10)!=10:gmsh.model.mesh.optimize('Netgen')
        gmsh.model.mesh.setOrder(2)
        from .curved_mesh import place_midsides
        projection=place_midsides();print('CAD_MIDSIDE_PROJECTION',projection,flush=True)
        etypes,labels,raw=gmsh.model.mesh.getElements(3);qualities=gmsh.model.mesh.getElementQualities(np.concatenate(labels),'minDetJac')
        if np.min(qualities)<=0:
            gmsh.write(str(directory/'preoptimization.msh'))
            raise ValueError('Non-positive curved pipe Jacobian; refuse to solve this mesh')
        gmsh.write(str(directory/'geometry.step'));gmsh.write(str(directory/'mesh.msh'))
        tags,coord,_=gmsh.model.mesh.getNodes();tags=np.asarray(tags);order=np.argsort(tags);tags=tags[order];p=np.asarray(coord).reshape(-1,3)[order]
        tetrefs=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[.5,0,.5],[0,.5,.5]])
        cells=np.vstack([np.searchsorted(tags,np.asarray(c).reshape(-1,10)[:,native_permutation(t,tetrefs)]) for t,c in zip(etypes,raw) if t==11]).astype(np.int32)
        if any(t!=11 for t in etypes):raise ValueError('Expected Tet10')
        trirefs=np.array([[0,0],[1,0],[0,1],[.5,0],[.5,.5],[0,.5]])
        triangles=[]
        for dim,tag in surfaces:
            types,_,raw=gmsh.model.mesh.getElements(2,tag)
            for t,c in zip(types,raw):triangles.append(np.searchsorted(tags,np.asarray(c).reshape(-1,6)[:,native_permutation(t,trirefs)]))
        tri=np.vstack(triangles).astype(np.int32);used=np.unique(cells);remap=np.full(len(p),-1,dtype=np.int32);remap[used]=np.arange(len(used));sets={}
        for name,faces in {**{'cut_E'+k:v for k,v in cuts.items()},**({'fixed_nodes':clamp} if fixed else {})}.items():
            vals=np.unique(np.concatenate([gmsh.model.mesh.getNodes(2,t,includeBoundary=True)[0] for t in faces]));sets[name]=remap[np.searchsorted(tags,vals)]
        cells=remap[cells];tri=remap[tri];p=p[used]
        if np.any(tri<0):raise ValueError('Unconnected surface nodes')
        quality=gmsh.model.mesh.getElementQualities(np.concatenate(labels),'minDetJac')
        meta=dict(nodes=len(p),elements=len(cells),boundaryTriangles=len(tri),elementType='curved isoparametric Tet10',canonicalEdges=EDGES,nativeVolumes=1,cadVolumeM3=float(occ.getMass(3,volumes[0])),toeSize=fine,bodySize=body,focusSize=focus,minGmshDetJac=float(min(quality)),generationSeconds=time.time()-started,gmshVersion=gmsh.__version__,toeRings=0,seamCurves=0,shoulderRadiusM=0,toeRadiusM=0,analysisType=request['analysisType'])
        meta.update(cadTopologyAudit=topology_audit,boundaryProjectionAudit=projection)
        if meta['minGmshDetJac']<=0:raise ValueError('Non-positive pipe Jacobian')
        np.savez_compressed(directory/'mesh.npz',points=p,tetra10=cells,triangle6=tri,**sets)
        (directory/'mesh_meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');return meta
    finally:gmsh.finalize()
