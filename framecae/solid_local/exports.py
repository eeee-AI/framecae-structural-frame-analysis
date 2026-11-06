"""Portable native exports. Abaqus is optional and is not invoked here."""
import numpy as np
from pathlib import Path
from .boundary import cut_observations
from .tet10 import mises

def mean_equations(points,triangles,request,cut_sets,displacement):
    from scipy.linalg import qr
    from .submodel import sections
    _,_,_,_,operators=sections(points,triangles,request,cut_sets)
    if request['couplingMode']=='forceSubmodel':operators=operators[:1]
    equations=[];dummy=[];counter=len(points)
    for op in operators:
        C=op['C'];ids=op['ids'];desired=C@displacement[ids].ravel() if request['couplingMode']=='forceSubmodel' else np.r_[next(a['translation'] for a in request['arms'] if a['element']==op['element']),np.array(next(a['rotation'] for a in request['arms'] if a['element']==op['element']))*op['length']]
        pivots=qr(C,mode='economic',pivoting=True)[2][:6];transform=np.linalg.inv(C[:,pivots]);matrix=transform@C;values=transform@desired
        for i in range(6):
            counter+=1;dummy.append((counter,float(values[i])))
            terms=[(int(ids[pivots[i]//3])+1,int(pivots[i]%3)+1,1.)]
            terms.extend((int(ids[j//3])+1,int(j%3)+1,float(v)) for j,v in enumerate(matrix[i]) if j not in pivots and abs(v)>1e-13)
            terms.append((counter,1,-1.));equations.append(terms)
    return dummy,equations

def export(directory,request):
    import meshio
    directory=Path(directory);mesh=np.load(directory/'mesh.npz');solution=np.load(directory/'solution.npz')
    points=mesh['points'];cells=mesh['tetra10'];absolute=points+request['origin']
    meshio.write(directory/'result.vtu',meshio.Mesh(absolute,[('tetra10',cells)],point_data={'U_m':solution['displacement'],'von_Mises_nodal_average_MPa':solution['nodal_mises']/1e6},cell_data={'von_Mises_centroid_MPa':[mises(solution['centroid_stress'])/1e6]}))
    cut_sets={str(a['element']):mesh['cut_E'+str(a['element'])] for a in request['arms']} if all('cut_E'+str(a['element']) in mesh for a in request['arms']) else None
    cuts,fixed,values,_,_=cut_observations(points,request,cut_sets);loads=solution['loads']
    submodel=request.get('analysisType')!='idealClamp'
    dummy,equations=mean_equations(points,mesh['triangle6'],request,cut_sets,solution['displacement']) if submodel else ([],[])
    with (directory/'model.inp').open('w',encoding='ascii') as f:
        f.write('*HEADING\nFrameCAE self-solved curved Tet10: input for optional independent Abaqus check\n*NODE,NSET=ALLNODES\n')
        for i,p in enumerate(absolute,1):f.write('%d, %.16g, %.16g, %.16g\n'%(i,*p))
        for nid,_ in dummy:f.write('%d, %.16g, %.16g, %.16g\n'%(nid,*request['origin']))
        f.write('*ELEMENT,TYPE=C3D10,ELSET=SOLID\n')
        for i,c in enumerate(cells,1):f.write(str(i)+','+','.join(str(int(v)+1) for v in c)+'\n')
        for element,ids in cuts.items():
            f.write('*NSET,NSET=CUT_E'+element+'\n')
            for start in range(0,len(ids),16):f.write(','.join(str(int(n)+1) for n in ids[start:start+16])+'\n')
        for terms in equations:
            f.write('*EQUATION\n%d\n'%len(terms))
            for i in range(0,len(terms),4):f.write(', '.join('%d,%d,%.16g'%t for t in terms[i:i+4])+'\n')
        m=request['material'];f.write('*MATERIAL,NAME=STEEL\n*ELASTIC\n%.16g,%.16g\n*SOLID SECTION,ELSET=SOLID,MATERIAL=STEEL\n,\n*STEP,NAME=STATIC,NLGEOM=NO\n*STATIC\n1.,1.\n*BOUNDARY\n'%(m['E'],m['nu']))
        if submodel:
            for nid,value in dummy:f.write('%d,1,1,%.16g\n'%(nid,value))
        else:
            for n in mesh['fixed_nodes']:f.write('%d,1,3,0.\n'%(int(n)+1))
        f.write('*CLOAD\n')
        for n in np.flatnonzero(np.linalg.norm(loads,axis=1)>1e-14):
            for k in range(3):
                if abs(loads[n,k])>1e-14:f.write('%d,%d,%.16g\n'%(n+1,k+1,loads[n,k]))
        f.write('*OUTPUT,FIELD\n*NODE OUTPUT\nU,RF\n*ELEMENT OUTPUT\nS\n*END STEP\n')
