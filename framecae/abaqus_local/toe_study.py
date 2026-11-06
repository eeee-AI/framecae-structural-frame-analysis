"""Fixed weld-toe surface sampling; independent of mesh node numbering.

Stress tensors come from Abaqus ELEMENT_NODAL extrapolation, one-sided per
element, not the smoothed cloud. Midside surface nodes define small facets;
tensor components are interpolated on the nearest facet before Mises.
"""
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def mises(s):
    a,b,c,d,e,f=np.asarray(s).T
    return np.sqrt(((a-b)**2+(b-c)**2+(c-a)**2)/2+3*(d*d+e*e+f*f))


def toe_paths(request, angles=144, meridian=17):
    g=request['geometry'];paths={}
    for arm in request['arms']:
        g=arm.get('geometry',request['geometry'])
        d=np.asarray(arm['direction']);r=arm['outerRadius'];t=g['toeRadius']
        h=g['reinforcement'];w=g['weldWidth'];s=g['weldDistance']
        crown=(w*w/4+h*h)/(2*h)-t
        c1=np.array([r+t,s-w/2]);c2=np.array([r+h-crown,s])
        touch=c1+t/(t+crown)*(c2-c1)
        angle=np.linspace(np.pi,np.arctan2(*(touch-c1)[::-1]),meridian)
        profile=c1[:,None]+t*np.array([np.cos(angle),np.sin(angle)])
        basis=np.eye(3)[np.argmin(np.abs(d))];u=basis-d*np.dot(basis,d);u/=np.linalg.norm(u);v=np.cross(d,u)
        theta=np.arange(angles)*2*np.pi/angles
        radial=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
        for side in ['inner','outer']:
            axial=profile[1] if side=='inner' else 2*s-profile[1]
            pts=axial[None,:,None]*d+profile[0][None,:,None]*radial[:,None,:]
            paths['E%d_%s'%(arm['element'],side)]={'points':pts.reshape(-1,3),
                'shape':(angles,meridian),'element':arm['element'],'direction':d,
                'theta':np.repeat(theta,meridian),'arcFraction':np.tile(np.linspace(0,1,meridian),angles),
                'radius':r,'side':side,'basisU':u,'basisV':v}
    return paths


def sample_facets(points,triangles,tensors,samples,candidates=32):
    vertices=points[triangles]
    tree=cKDTree(vertices.mean(axis=1))
    _,ids=tree.query(samples,k=min(candidates,len(triangles)))
    if ids.ndim==1:ids=ids[:,None]
    p=vertices[ids];a=p[:,:,0];v0=p[:,:,1]-a;v1=p[:,:,2]-a;v2=samples[:,None]-a
    dot=lambda x,y:np.einsum('...i,...i->...',x,y)
    d00=dot(v0,v0);d01=dot(v0,v1);d11=dot(v1,v1);d20=dot(v2,v0);d21=dot(v2,v1)
    den=np.maximum(d00*d11-d01*d01,1e-30)
    b=(d11*d20-d01*d21)/den;c=(d00*d21-d01*d20)/den
    weights=np.stack((1-b-c,b,c),axis=2)
    weights=np.maximum(weights,0);weights/=weights.sum(axis=2)[:,:,None]
    projected=np.einsum('nkj,nkji->nki',weights,p)
    distances=np.linalg.norm(projected-samples[:,None],axis=2)
    best=np.argmin(distances,axis=1);row=np.arange(len(samples));chosen=ids[row,best]
    stress=np.einsum('nj,njc->nc',weights[row,best],tensors[chosen])
    return mises(stress),distances[row,best],chosen


def analyze(folder,angles=144,meridian=17,filename='toe_samples.json'):
    folder=Path(folder);q=json.loads((folder/'local_request.json').read_text('utf-8'))
    raw=np.load(folder/'toe_fields.npz');points=raw['points'];faces=raw['faces'];stress=raw['surfaceTensor']
    vertices=points[faces];centers=vertices.mean(axis=1);paths=toe_paths(q,angles,meridian);records={};samples={}
    ht=q['mesh']['toeSize'];g=q['geometry']
    for name,path in paths.items():
        arm=next(a for a in q['arms'] if a['element']==path['element'])
        g=arm.get('geometry',q['geometry'])
        d=path['direction'];axial=centers@d;radial=np.linalg.norm(centers-axial[:,None]*d,axis=1)
        # Includes both sides and crown, excludes the inner bore and remote caps.
        keep=(np.abs(axial-g['weldDistance'])<g['weldWidth']/2+max(.008,2*ht))&(radial>path['radius']-.002)
        selected=np.flatnonzero(keep)
        if len(selected)<10:raise ValueError('Missing outer weld surface '+name)
        values,gaps,chosen=sample_facets(points,faces[selected],stress[selected],path['points'])
        peak=int(np.argmax(values));samples[name]=values.tolist()
        # Search every one-sided boundary-node value on the same analytic toe
        # surface. A fixed angular sample grid alone can miss an element peak.
        va=vertices@d;vr=np.linalg.norm(vertices-va[:,:,None]*d,axis=2)
        sample_axial=path['points']@d;station=g['weldDistance']+(-1 if path['side']=='inner' else 1)*g['weldWidth']/2
        circle_distance=np.sqrt((vr-(path['radius']+g['toeRadius']))**2+(va-station)**2)
        mask=(va>=sample_axial.min()-1e-7)&(va<=sample_axial.max()+1e-7)&(np.abs(circle_distance-g['toeRadius'])<1e-7)
        flat=np.flatnonzero(mask)
        if len(flat)<10:raise ValueError('Too few actual toe-surface nodes '+name)
        boundary_values=mises(stress.reshape(-1,6)[flat].astype(float));pmax=int(np.argmax(boundary_values))
        point=vertices.reshape(-1,3)[flat[pmax]];a=float(point@d);radial_point=point-a*d
        theta=float(np.arctan2(radial_point@path['basisV'],radial_point@path['basisU'])%(2*np.pi))
        sign=1 if path['side']=='inner' else -1
        end=path['points'].reshape(angles,meridian,3)[0,-1];end_a=float(end@d)
        end_phi=np.arctan2((end_a-station)*sign,np.linalg.norm(end-end_a*d)-(path['radius']+g['toeRadius']))
        phi=np.arctan2((a-station)*sign,np.linalg.norm(radial_point)-(path['radius']+g['toeRadius']))%(2*np.pi)
        arc_fraction=float(np.clip((np.pi-phi)/(np.pi-end_phi),0,1))
        records[name]={'peakMises':float(boundary_values[pmax]),'samplePeakMises':float(values[peak]),
            'meanMises':float(values.mean()),'thetaDegrees':float(np.degrees(theta)),
            'arcFraction':arc_fraction,'peakPoint':point.tolist(),
            'samplePeakPoint':path['points'][peak].tolist(),'boundaryValueCount':int(len(flat)),
            'peakDefinition':'maximum of ALL one-sided element-nodal values on the fixed analytic toe surface',
            'maxProjectionGap':float(gaps.max()),
            'p95ProjectionGap':float(np.percentile(gaps,95)),'sampleCount':len(values),
            'sampleShape':list(path['shape']),'resolutionPassed':bool(gaps.max()<.10*ht),
            'definition':'one-sided Abaqus element-nodal tensor; facet interpolation at fixed analytic toe points'}
    result={'metricRevision':2,'toeSize':ht,'records':records,'samples':samples,
            'sampling':{'angles':angles,'meridian':meridian,'projectionGapLimit':.10*ht,'tensorAveragedBetweenElements':False}}
    (folder/filename).write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    return result


def audit_geometry(request,audit):
    g=request['geometry'];r=request['arms'][0]['outerRadius'];t=g['toeRadius'];h=g['reinforcement'];w=g['weldWidth']
    crown=(w*w/4+h*h)/(2*h)-t
    centers=np.array([r+t,-w/2])-np.array([r+h-crown,0])
    tangent_gap=abs(float(np.linalg.norm(centers))-(t+crown))
    count=sum(abs(row['radius']-t)<1e-7 for row in audit.get('measuredEdgeRadii',[]))
    return {'passed':audit.get('nativeCellCount')==1 and count>=6 and tangent_gap<1e-10,
        'nativeCellCount':audit.get('nativeCellCount'),'toeRadius':t,'nativeToeArcCount':count,
        'analyticTangencyError':tangent_gap,'fullPenetration':'continuous identical elastic solid assumption'}


def audit_mesh(folder):
    folder=Path(folder);mesh=json.loads((folder/'mesh.json').read_text('utf-8'))
    meta=json.loads((folder/'mesh_meta.json').read_text('utf-8'))
    elements=np.asarray(mesh['elements'],dtype=np.int32);faces=np.asarray(meta['faces'],dtype=np.int32)
    starts=np.repeat(elements[:,0],elements.shape[1]-1);ends=elements[:,1:].ravel()
    graph=coo_matrix((np.ones(len(starts),dtype=np.int8),(starts,ends)),shape=(len(mesh['nodes']),len(mesh['nodes']))).tocsr()
    count,_=connected_components(graph,directed=False)
    edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
    _,uses=np.unique(edges,axis=0,return_counts=True)
    return {'connectedComponents':int(count),'surfaceNonmanifoldEdges':int(np.count_nonzero(uses!=2)),
            'surfaceClosed':bool(np.all(uses==2)),'nodeCount':len(mesh['nodes']),'elementCount':len(elements),
            'passed':bool(count==1 and np.all(uses==2))}


def compare(a,b):
    changes={}
    for key,x in a['samples'].items():
        x=np.asarray(x);y=np.asarray(b['samples'][key]);reference=max(b['records'][key]['peakMises'],1.)
        changes[key]={'peakRelativeChange':float(abs(a['records'][key]['peakMises']-b['records'][key]['peakMises'])/reference),
            'profileMaxRelativeChange':float(np.max(np.abs(x-y))/reference),
            'profileRmsRelativeChange':float(np.linalg.norm(x-y)/np.sqrt(len(x))/reference),
            'peakAbsoluteChangePa':float(abs(a['records'][key]['peakMises']-b['records'][key]['peakMises']))}
    peaks=all(v['peakRelativeChange']<=.05 for v in changes.values())
    profiles=all(v['profileMaxRelativeChange']<=.05 for v in changes.values())
    return {'changes':changes,'passed':peaks and profiles,'peakPassed':peaks,'profilePassed':profiles,
            'criterion':'peak <= 5% and full fixed profile max difference <= 5%, reported separately'}
