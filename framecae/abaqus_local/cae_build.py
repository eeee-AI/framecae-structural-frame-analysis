# -*- coding: utf-8 -*-
"""Run with abaqus cae noGUI=cae_build.py -- absolute_request_path."""
import json
import math
import os
from pathlib import Path
import sys
import traceback

from abaqus import mdb
from abaqusConstants import *
import mesh as abaqus_mesh
import numpy as np

sys.path.insert(0,str(Path(globals().get('__file__',str(Path.cwd()/'cae_build.py'))).resolve().parent))
try:
    from mesh_ops import write_input
except ImportError:
    from framecae.abaqus_local.mesh_ops import write_input


def build(request_path):
    path=Path(request_path);folder=path.parent
    request=json.loads(path.read_text(encoding='utf-8'))
    g=request['geometry'];h=request['mesh']['size'];hf=request['mesh']['focusSize']
    complex_node=request.get('schemaVersion',1)>=2
    hub=g['hubRadius'];r=request['arms'][0]['outerRadius'];ri=request['arms'][0]['innerRadius']
    model=mdb.Model(name='NativeGeometry')
    assembly=model.rootAssembly;assembly.DatumCsysByDefault(CARTESIAN)

    def revolve(name,draw):
        sketch=model.ConstrainedSketch(name='S_'+name,sheetSize=4)
        sketch.ConstructionLine(point1=(0,-2),point2=(0,2))
        draw(sketch)
        part=model.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY)
        part.BaseSolidRevolve(sketch=sketch,angle=360.0,flipRevolveDirection=OFF)
        return part

    def sphere(sk):
        sk.Arc3Points(point1=(0,-hub),point2=(0,hub),point3=(hub,0))
        sk.Line(point1=(0,hub),point2=(0,-hub))
    core=revolve('Core',sphere)
    objects=[assembly.Instance(name='Core',part=core,dependent=ON)]

    def orient(instance,direction):
        # Revolve axis is the global sketch Y axis.
        y=np.array([0.,1.,0.]);d=np.array(direction);axis=np.cross(y,d)
        cosine=float(np.clip(y@d,-1,1))
        if np.linalg.norm(axis)>1e-10:
            assembly.rotate(instanceList=(instance.name,),axisPoint=(0,0,0),axisDirection=tuple(axis),angle=math.degrees(math.acos(cosine)))
        elif cosine<0:
            assembly.rotate(instanceList=(instance.name,),axisPoint=(0,0,0),axisDirection=(1,0,0),angle=180)

    for index,arm in enumerate(request['arms']):
        ag=arm.get('geometry',g)
        length=arm['length'];center=ag['weldDistance'];width=ag['weldWidth'];height=ag['reinforcement'];toe=ag['toeRadius']
        left=center-width/2;right=center+width/2
        crown=(width*width/4+height*height)/(2*height)-toe
        # Three exactly tangent circular arcs: concave toe, convex crown, concave toe.
        c1=np.array([r+toe,left]);c2=np.array([r+height-crown,center])
        touch=c1+toe/(toe+crown)*(c2-c1)
        start=np.array([r,left]);end=np.array([r,right])
        v1=(start-c1)/toe;v2=(touch-c1)/toe;mid=c1+toe*(v1+v2)/np.linalg.norm(v1+v2)
        mirror=lambda p: (float(p[0]),float(2*center-p[1]))
        def outline(sk):
            root=hub*.45
            sk.Line(point1=(r,root),point2=(r,left))
            sk.Arc3Points(point1=tuple(start),point2=tuple(touch),point3=tuple(mid))
            sk.Arc3Points(point1=tuple(touch),point2=mirror(touch),point3=(r+height,center))
            sk.Arc3Points(point1=mirror(touch),point2=tuple(end),point3=mirror(mid))
            sk.Line(point1=tuple(end),point2=(r,length))
            sk.Line(point1=(r,length),point2=(0,length))
            sk.Line(point1=(0,length),point2=(0,root))
            sk.Line(point1=(0,root),point2=(r,root))
        part=revolve('Arm%d'%index,outline)
        instance=assembly.Instance(name=part.name,part=part,dependent=ON)
        orient(instance,arm['direction']);objects.append(instance)
    assembly.regenerate()
    premerge={obj.name:assembly.getMassProperties(regions=(obj,)) for obj in objects}
    (folder/'premerge.json').write_text(json.dumps(premerge,default=str,indent=2),encoding='utf-8')
    merged=assembly.InstanceFromBooleanMerge(name='Outer',instances=tuple(objects),keepIntersections=OFF,originalInstances=SUPPRESS,domain=GEOMETRY)
    outer=model.parts['Outer']
    join_edges=[];shoulder_groups={}
    station=math.sqrt(hub*hub-r*r)
    for arm in request['arms']:
        found=[]
        for edge in outer.edges:
            p=np.array(edge.pointOn[0])
            if abs(p@np.array(arm['direction'])-station)<1e-5 and abs(np.linalg.norm(p)-hub)<1e-5:
                try:
                    if abs(edge.getRadius()-r)<1e-5:found.append(edge)
                except Exception:pass
        shoulder_groups[str(arm['element'])]=[e.index for e in found]
        for e in found:
            if e.index not in [v.index for v in join_edges]:join_edges.append(e)
    # A circular shoulder can be split at the sphere's parametric seam.
    if (complex_node and any(not v for v in shoulder_groups.values())) or (not complex_node and (len(join_edges)<3 or len(join_edges)>6)):
        mdb.saveAs(pathName=str(folder/'geometry_error.cae'))
        raise RuntimeError('Missing shoulder circles: %s'%shoulder_groups)
    outer.Round(radius=g['blendWidth'],edgeList=tuple(join_edges))
    assembly.regenerate()
    cutters=[]
    for index,arm in enumerate(request['arms']):
        def bore(sk):
            a=g['boreStart'];b=a+ri;end=arm['length']+.03
            # A true hemispherical blind end has a smooth pole on the axis.
            # A radius smoothstep reaching zero produces an axial cusp instead.
            sk.Arc3Points(point1=(0,a),point2=(ri,b),point3=(ri/math.sqrt(2),b-ri/math.sqrt(2)))
            sk.Line(point1=(ri,b),point2=(ri,end))
            sk.Line(point1=(ri,end),point2=(0,end))
            sk.Line(point1=(0,end),point2=(0,a))
        part=revolve('Bore%d'%index,bore)
        instance=assembly.Instance(name=part.name,part=part,dependent=ON)
        orient(instance,arm['direction']);cutters.append(instance)
    cut=assembly.InstanceFromBooleanCut(name='Hub',instanceToBeCut=merged,cuttingInstances=tuple(cutters),originalInstances=SUPPRESS)
    part=model.parts['Hub']
    # Keep actual CAD end faces associated with each branch before meshing.
    cut_faces={}
    if complex_node:
        for arm in request['arms']:
            selected=[];d=np.asarray(arm['direction'])
            for face in part.faces:
                p=np.asarray(face.pointOn[0]);radial=np.linalg.norm(p-(p@d)*d)
                if abs(p@d-arm['length'])<1e-7 and arm['innerRadius']-1e-7<=radial<=arm['outerRadius']+1e-7:
                    selected.append(face)
            if not selected:raise RuntimeError('No CAD cut face for E%d'%arm['element'])
            part.Set(name='CUT_E%d'%arm['element'],faces=tuple(selected))
            cut_faces[str(arm['element'])]=selected
    diagnostics={}
    for name,p in model.parts.items():
        xyz=np.array([v.pointOn[0] for v in p.vertices])
        diagnostics[name]={'cells':len(p.cells),'vertices':len(p.vertices),
                           'low':xyz.min(axis=0).tolist() if len(xyz) else None,
                           'high':xyz.max(axis=0).tolist() if len(xyz) else None}
    (folder/'geometry_diagnostics.json').write_text(json.dumps(diagnostics,indent=2),encoding='utf-8')
    if os.environ.get('FRAMECAE_GEOMETRY_ONLY')=='1':
        mdb.saveAs(pathName=str(folder/'geometry_debug.cae'))
        return
    # The full-penetration weld and base metal have the same elastic material.
    # Their continuous native solid is meshed conformingly; element-centroid
    # bands label the weld volume for reporting, without an artificial interface.
    part.setMeshControls(regions=part.cells[:],elemShape=TET,technique=FREE)
    part.setElementType(regions=(part.cells[:],),elemTypes=(abaqus_mesh.ElemType(elemCode=C3D10,elemLibrary=STANDARD),))
    part.seedPart(size=h,deviationFactor=.08,minSizeFactor=.15)
    fine=[];toe_edges=[];radius_checks=[]
    for edge in part.edges:
        p=np.array(edge.pointOn[0]);norm=np.linalg.norm(p)
        seam_edge=any(abs(float(p@np.array(a['direction']))-a.get('geometry',g)['weldDistance'])<a.get('geometry',g)['weldWidth']*.65
                      and np.linalg.norm(p-(p@np.array(a['direction']))*np.array(a['direction']))<r+g['reinforcement']*2 for a in request['arms'])
        if norm<hub+g['blendWidth']+r*.2 or seam_edge:
            fine.append(edge)
        if seam_edge:toe_edges.append(edge)
        try:radius_checks.append({'point':p.tolist(),'radius':float(edge.getRadius())})
        except Exception:pass
    if fine: part.seedEdgeBySize(edges=tuple(fine),size=hf,deviationFactor=.08,minSizeFactor=.1,constraint=FINER)
    ht=request['mesh'].get('toeSize',hf)
    if toe_edges:part.seedEdgeBySize(edges=tuple(toe_edges),size=ht,deviationFactor=.03,minSizeFactor=.1,constraint=FINER)
    mesh_attempts=[];effective_focus=hf
    for factor in (1.,.95,.90):
        if factor!=1.:
            part.deleteMesh()
            effective_focus=hf*factor
            if fine:part.seedEdgeBySize(edges=tuple(fine),size=effective_focus,deviationFactor=.08,minSizeFactor=.1,constraint=FINER)
            if toe_edges:part.seedEdgeBySize(edges=tuple(toe_edges),size=ht*factor,deviationFactor=.03,minSizeFactor=.1,constraint=FINER)
        part.generateMesh(seedConstraintOverride=OFF if factor==1. else ON,meshTechniqueOverride=ON)
        mesh_attempts.append({'algorithm':'default','focusSize':effective_focus,'elements':len(part.elements)})
        if len(part.elements)>=10:break
    quality=part.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
    quality_counts={k:len(v) if hasattr(v,'__len__') else str(v) for k,v in quality.items()}
    if quality_counts.get('failedElements',0) not in (0,'0'):
        raise RuntimeError('Mesh has elements that fail Abaqus analysis checks')
    if len(part.nodes)<10 or len(part.elements)<10:
        raise RuntimeError('Native solid mesh generation failed')
    if len(part.nodes)>1000000:
        raise RuntimeError('Mesh exceeds 1000000 nodes; increase mesh sizes')
    node_map={n.label:i for i,n in enumerate(part.nodes)}
    mesh={'nodes':[list(n.coordinates) for n in part.nodes],
          'elements':[[node_map[n.label] for n in e.getNodes()] for e in part.elements],
          'elementType':'C3D10','nativeCellCount':len(part.cells),'surfaceFitted':True,
          'regionAssignment':'element centroid within nominal weld axial band; same elastic material',
          'meshQuality':quality_counts,'meshingAttempts':mesh_attempts,'effectiveFocusSize':effective_focus,
          'effectiveToeSize':ht*factor,
          'geometryAudit':{'nativeCellCount':len(part.cells),'toeSeedEdges':len(toe_edges),
                           'measuredEdgeRadii':radius_checks,'sectionConsistency':request.get('sectionAudit')}}
    if complex_node:
        cut_sets={}
        for key,faces in cut_faces.items():
            labels=set()
            for face in faces:
                labels.update(n.label for n in face.getNodes())
            if len(labels)<6:raise RuntimeError('CAD cut node set is empty for E'+key)
            cut_sets[key]=sorted(node_map[label] for label in labels)
        mesh['cutNodeSets']=cut_sets
        mesh['geometryAudit']['shoulderEdgeGroups']=shoulder_groups
        mesh['geometryAudit']['cutSelection']='named native CAD end faces, including midside nodes'
    (folder/'mesh.json').write_text(json.dumps(mesh),encoding='utf-8')
    meta=write_input(folder,request,mesh)
    mdb.ModelFromInputFile(name='Analysis',inputFileName=str(folder/'model.inp'))
    mdb.saveAs(pathName=str(folder/'model.cae'))
    (folder/'build_result.json').write_text(json.dumps({'ok':True,'nodes':len(part.nodes),'elements':len(part.elements),
        'weldElements':{k:len(v) for k,v in meta['regions'].items() if k.startswith('WELD')},'nativeCellCount':len(part.cells)}),encoding='utf-8')


if __name__=='__main__':
    try:
        build(sys.argv[-1])
    except BaseException:
        Path('build_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
