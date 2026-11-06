"""NumPy-only mesh/transfer utilities, usable from Abaqus Python as well."""
import json
from pathlib import Path
import numpy as np


def boundary_triangles(elements, element_type):
    faces={}
    tet=element_type=='C3D10'
    patterns=((0,2,1),(0,1,3),(1,2,3),(2,0,3)) if tet else (
        (0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    for owner,conn in enumerate(elements):
        for pattern in patterns:
            face=[conn[i] for i in pattern]
            key=tuple(sorted(face))
            if key in faces:
                faces[key]=None
            elif tet:
                mids={(min(conn[a],conn[b]),max(conn[a],conn[b])):conn[m] for a,b,m in
                      ((0,1,4),(1,2,5),(2,0,6),(0,3,7),(1,3,8),(2,3,9))}
                a,b,c=face
                ab=mids[tuple(sorted((a,b)))];bc=mids[tuple(sorted((b,c)))];ca=mids[tuple(sorted((c,a)))]
                faces[key]=(owner,[(a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)])
            else:
                a,b,c,d=face
                faces[key]=(owner,[(a,b,c),(a,c,d)])
    triangles=[];owners=[]
    for value in faces.values():
        if value is not None:
            owner,tris=value
            triangles.extend(tris);owners.extend([owner]*len(tris))
    return np.asarray(triangles,dtype=int),np.asarray(owners,dtype=int)


def prescribe_cuts(points,request,cut_node_sets=None):
    points=np.asarray(points)
    prescribed={};cut_ids={}
    for arm in request['arms']:
        d=np.array(arm['direction']);c=np.array(arm['center'])
        if cut_node_sets is not None:
            ids=np.asarray(cut_node_sets[str(arm['element'])],dtype=int)
        else:
            axial=points@d;radial=np.linalg.norm(points-axial[:,None]*d,axis=1)
            mask=np.abs(axial-arm['length'])<max(1e-8,arm['length']*1e-7)
            if request.get('schemaVersion',1)>=2:
                mask &= (radial>=arm['innerRadius']-1e-7)&(radial<=arm['outerRadius']+1e-7)
            ids=np.flatnonzero(mask)
        if np.max(np.abs(points[ids]@d-arm['length']),initial=0)>1e-6:
            raise ValueError('CAD cut set contains off-plane nodes')
        if len(ids)<6:
            raise ValueError('E%d cut has too few nodes'%arm['element'])
        u=np.array(arm['translation'])+np.cross(np.array(arm['rotation']),points[ids]-c)
        for i,value in zip(ids,u):
            if int(i) in prescribed and not np.allclose(prescribed[int(i)],value,atol=1e-10):
                raise ValueError('Conflicting cut constraints')
            prescribed[int(i)]=value.tolist()
        cut_ids[str(arm['element'])]=ids.tolist()
    return prescribed,cut_ids


def distribute_load(points,triangles,request,excluded=()):
    points=np.asarray(points);triangles=np.asarray(triangles)
    target=np.asarray(request['load']['wrench'])
    if np.linalg.norm(target)==0:
        return np.array([],dtype=int),np.empty((0,3)),np.zeros(6)
    d=np.array(request['load']['direction']);radius=request['load']['radius']
    hub=request['geometry']['hubRadius']
    vertices=points[triangles];centers=vertices.mean(axis=1)
    axial=centers@d;radial=np.linalg.norm(centers-axial[:,None]*d,axis=1)
    selected=(axial>np.sqrt(hub*hub-radius*radius)*.97)&(radial<radius)&(np.linalg.norm(centers,axis=1)<hub*1.08)
    weights=np.zeros(len(points))
    areas=np.linalg.norm(np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0]),axis=1)/2
    np.add.at(weights,triangles[selected].ravel(),np.repeat(areas[selected]/3,3))
    if len(excluded): weights[np.asarray(list(excluded),dtype=int)]=0
    ids=np.flatnonzero(weights>0)
    if len(ids)<6:
        raise ValueError('Bearing cap has too few nodes; change load direction/radius or refine mesh')
    w=weights[ids];w/=w.sum()
    x,y,z=points[ids].T
    matrices=np.zeros((len(ids),6,3));matrices[:,:3,:]=np.eye(3)
    matrices[:,3:,:]=np.stack((np.stack((0*x,-z,y),axis=1),np.stack((z,0*x,-x),axis=1),
                             np.stack((-y,x,0*x),axis=1)),axis=1)
    gram=np.einsum('i,iaj,ibj->ab',w,matrices,matrices)
    values=w[:,None]*np.einsum('iaj,a->ij',matrices,np.linalg.solve(gram,target))
    recovered=np.einsum('iaj,ij->a',matrices,values)
    if not np.allclose(recovered,target,rtol=1e-9,atol=1e-6):
        raise ValueError('Bearing cap force/moment transfer failed')
    return ids,values,recovered


def element_regions(points,elements,request):
    centers=np.asarray(points)[np.asarray(elements)[:,:4]].mean(axis=1)
    g=request['geometry'];regions={};weld_mask=np.zeros(len(elements),dtype=bool)
    for arm in request['arms']:
        ag=arm.get('geometry',g)
        axial=centers@np.asarray(arm['direction'])
        radial=np.linalg.norm(centers-axial[:,None]*np.array(arm['direction']),axis=1)
        mask=(np.abs(axial-ag['weldDistance'])<=ag['weldWidth']/2+1e-8)&(radial<=arm['outerRadius']+ag['reinforcement']*1.2)
        name='WELD_E%d'%arm['element']
        regions[name]=np.flatnonzero(mask).tolist();weld_mask|=mask
    regions['BODY']=np.flatnonzero(~weld_mask).tolist()
    # Fixed physical shoulder volume; its mean is a regional metric, not a weld hot spot.
    shoulder=np.zeros(len(elements),dtype=bool)
    for arm in request['arms']:
        axial=centers@np.asarray(arm['direction'])
        radial=np.linalg.norm(centers-axial[:,None]*np.array(arm['direction']),axis=1)
        shoulder|=(axial>.55*g['hubRadius'])&(axial<g['hubRadius']+g['blendWidth'])&(radial>.8*arm['innerRadius'])
    regions['SHOULDER']=np.flatnonzero(shoulder&~weld_mask).tolist()
    regions['PIPE']=np.flatnonzero((np.linalg.norm(centers,axis=1)>g['hubRadius']+g['blendWidth'])&~weld_mask).tolist()
    return regions


def write_input(directory,request,mesh):
    directory=Path(directory)
    points=np.array(mesh['nodes']);elements=mesh['elements'];etype=mesh['elementType']
    faces,owners=boundary_triangles(elements,etype)
    prescribed,cuts=prescribe_cuts(points,request,mesh.get('cutNodeSets'))
    vertices=points[faces]
    areas=np.linalg.norm(np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0]),axis=1)/2
    cut_areas={}
    for arm in request['arms']:
        mask=np.all(np.isin(faces,np.array(cuts[str(arm['element'])])),axis=1)
        expected=np.pi*(arm['outerRadius']**2-arm['innerRadius']**2)
        actual=float(areas[mask].sum())
        if abs(actual-expected)/expected>.05:
            raise ValueError('E%d cut area does not match its hollow circular section'%arm['element'])
        cut_areas[str(arm['element'])]={'meshArea':actual,'sectionArea':expected,'relativeDifference':abs(actual-expected)/expected}
    ids,forces,recovered=distribute_load(points,faces,request,prescribed)
    coupled=request.get('schemaVersion',1)>=2 and len(ids)>0
    load_reference=len(points)+1
    regions=element_regions(points,elements,request)
    if any(not regions['WELD_E%d'%arm['element']] for arm in request['arms']):
        raise ValueError('A weld band has no elements; refine or partition the weld region')
    lines=['*HEADING','FrameCAE 03 integral hub plus full-penetration ring welds', '*NODE,NSET=ALLNODES']
    lines.extend('%d, %.12g, %.12g, %.12g'%(i+1,*p) for i,p in enumerate(points))
    if coupled:lines.append('%d, 0., 0., 0.'%load_reference)
    lines.append('*ELEMENT,TYPE=%s,ELSET=ALLSOLID'%etype)
    lines.extend('%d, '%(i+1)+', '.join(str(int(n)+1) for n in conn) for i,conn in enumerate(elements))
    for name,indices in regions.items():
        if not indices: continue
        lines.append('*ELSET,ELSET='+name)
        for start in range(0,len(indices),16): lines.append(', '.join(str(i+1) for i in indices[start:start+16]))
    m=request['material']
    lines.extend(['*MATERIAL,NAME=STEEL','*ELASTIC','%.12g, %.12g'%(m['E'],m['nu']),
                  '*DENSITY','%.12g'%m['density']])
    for name in ['BODY']+['WELD_E%d'%a['element'] for a in request['arms']]:
        lines.extend(['*SOLID SECTION,ELSET=%s,MATERIAL=STEEL'%name,','])
    if coupled:
        lines.append('*SURFACE,TYPE=NODE,NAME=BEARING_PATCH')
        weights=np.zeros(len(points))
        eligible=np.all(np.isin(faces,ids),axis=1)
        np.add.at(weights,faces[eligible].ravel(),np.repeat(areas[eligible]/3,3))
        w=weights[ids]
        if np.any(w<=0):w=np.ones(len(ids))
        w=w/w.sum()
        lines.extend('%d,%.14g'%(i+1,v) for i,v in zip(ids,w))
        lines.extend(['*COUPLING,CONSTRAINT NAME=BEARING_LOAD,REF NODE=%d,SURFACE=BEARING_PATCH'%load_reference,
                      '*DISTRIBUTING,COUPLING=CONTINUUM','1,6'])
    lines.extend(['*STEP,NAME=STATIC,NLGEOM=NO','*STATIC','1.,1.','*BOUNDARY'])
    for i,u in prescribed.items():
        lines.extend('%d,%d,%d,%.14g'%(i+1,k+1,k+1,v) for k,v in enumerate(u))
    if len(ids):
        lines.append('*CLOAD')
        if coupled:
            lines.extend('%d,%d,%.14g'%(load_reference,k+1,v) for k,v in enumerate(request['load']['wrench']) if abs(v)>1e-14)
        else:
            for i,f in zip(ids,forces):
                lines.extend('%d,%d,%.14g'%(i+1,k+1,v) for k,v in enumerate(f) if abs(v)>1e-14)
    gravity=np.array(request['gravity']);mag=np.linalg.norm(gravity)
    if mag:
        lines.extend(['*DLOAD','ALLSOLID,GRAV,%.12g,%.12g,%.12g,%.12g'%(mag,*(gravity/mag))])
    lines.extend(['*OUTPUT,FIELD','*NODE OUTPUT','U,RF','*ELEMENT OUTPUT,POSITION=INTEGRATION POINT',
                  'S,IVOL,COORD','*ELEMENT OUTPUT','EVOL','*END STEP'])
    (directory/'model.inp').write_text('\n'.join(lines)+'\n',encoding='ascii')
    meta={'faces':faces.tolist(),'faceOwners':owners.tolist(),'cuts':cuts,'prescribed':prescribed,
          'loadIds':ids.tolist(),'loadValues':forces.tolist(),'recoveredWrench':recovered.tolist(),
          'regions':regions,'elementType':etype,'cutAreas':cut_areas}
    meta['loadTransfer']='continuumDistributingCoupling' if coupled else 'equivalentNodalForces'
    meta['loadReferenceNode']=load_reference if coupled else None
    (directory/'mesh_meta.json').write_text(json.dumps(meta),encoding='utf-8')
    return meta
