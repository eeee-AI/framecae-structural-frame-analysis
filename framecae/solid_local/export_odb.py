"""Run with Abaqus Python; writes our computed fields without running Abaqus/Standard."""
from pathlib import Path
import json,sys
import numpy as np
from odbAccess import Odb,openOdb
from abaqusConstants import THREE_D,DEFORMABLE_BODY,TIME,VECTOR,TENSOR_3D_FULL,SCALAR,NODAL,ELEMENT_NODAL,MISES


def export(directory):
    directory=Path(directory).resolve();request=json.loads((directory/'local_request.json').read_text('utf-8'))
    with np.load(directory/'mesh.npz') as z:p=z['points'];cells=z['tetra10'];tri=z['triangle6']
    with np.load(directory/'solution.npz') as z:u=z['displacement'];rf=z['reaction'];s=z['element_nodal_stress'];avg=z['nodal_mises']
    path=directory/'standalone_result.odb'
    odb=Odb(name='Standalone_N%d_Tet10'%request['node'],analysisTitle='Self-solved linear elasticity; Abaqus used only for visualization',description='SI m N Pa; stress order 11 22 33 12 13 23; one-sided direct FE element-nodal stress',path=str(path))
    try:
        part=odb.Part(name='N%d_HUB'%request['node'],embeddedSpace=THREE_D,type=DEFORMABLE_BODY)
        absolute=p+np.asarray(request['origin'])
        for start in range(0,len(p),10000):part.addNodes(nodeData=tuple((i+1,*map(float,absolute[i])) for i in range(start,min(start+10000,len(p)))),nodeSetName='ALL_NODES_'+str(start))
        for start in range(0,len(cells),5000):part.addElements(elementData=tuple((i+1,*map(int,cells[i]+1)) for i in range(start,min(start+5000,len(cells)))),type='C3D10')
        instance=odb.rootAssembly.Instance(name='N%d_HUB-1'%request['node'],object=part)
        for arm in request['arms']:
            ids=np.flatnonzero(np.abs(p@np.asarray(arm['direction'])-arm['length'])<1e-7)
            instance.NodeSetFromNodeLabels(name='CUT_E'+str(arm['element']),nodeLabels=tuple(map(int,ids+1)))
        for sample_file in ['toe_samples.npz','shoulder_samples.npz']:
            if not (directory/sample_file).exists():continue
            with np.load(directory/sample_file) as samples:
                for key in samples.files:
                    if key.endswith('_triangles'):
                        ids=np.unique(tri[samples[key]])
                        label=key[:-10].upper()+('_SHOULDER' if sample_file.startswith('shoulder') else '')
                        instance.NodeSetFromNodeLabels(name=label,nodeLabels=tuple(map(int,ids+1)))
        step=odb.Step(name='SELF_SOLVED',description='Computed by standalone NumPy/SciPy solver, not Abaqus',domain=TIME,timePeriod=1.)
        frame=step.Frame(incrementNumber=1,frameValue=1.,description='Standalone solution')
        fields={name:frame.FieldOutput(name=name,description=desc,type=VECTOR) for name,desc in [('U','Standalone nodal displacement, m'),('RF','Standalone nodal residual / boundary reaction, N')]}
        for start in range(0,len(p),10000):
            end=min(start+10000,len(p));labels=tuple(range(start+1,end+1))
            for name,value in [('U',u),('RF',rf)]:fields[name].addData(position=NODAL,instance=instance,labels=labels,data=tuple(map(tuple,value[start:end].astype(float))))
        field=frame.FieldOutput(name='S',description='Standalone directly evaluated one-sided stress, Pa',type=TENSOR_3D_FULL,
            componentLabels=('S11','S22','S33','S12','S13','S23'),validInvariants=(MISES,))
        vmfield=frame.FieldOutput(name='S_MISES_MPA',description='Standalone one-sided element-nodal Mises, MPa',type=SCALAR)
        avgfield=frame.FieldOutput(name='S_AVERAGED_MPA',description='Volume-weighted nodal tensor then Mises, MPa',type=SCALAR)
        for start in range(0,len(cells),2500):
            end=min(start+2500,len(cells));labels=tuple(range(start+1,end+1));values=s[start:end].reshape(-1,6).astype(float)
            a,b,c,d,e,f=values.T;vm=np.sqrt(.5*((a-b)**2+(b-c)**2+(c-a)**2)+3*(d*d+e*e+f*f))/1e6
            field.addData(position=ELEMENT_NODAL,instance=instance,labels=labels,data=tuple(map(tuple,values)))
            vmfield.addData(position=ELEMENT_NODAL,instance=instance,labels=labels,data=tuple((float(v),) for v in vm))
        for start in range(0,len(p),10000):
            end=min(start+10000,len(p));avgfield.addData(position=NODAL,instance=instance,labels=tuple(range(start+1,end+1)),data=tuple((float(v/1e6),) for v in avg[start:end]))
        odb.save()
    finally:odb.close()
    check=openOdb(str(path),readOnly=True)
    try:
        fields=check.steps['SELF_SOLVED'].frames[-1].fieldOutputs
        count=len(fields['S'].values)
        if count!=len(cells)*10:raise ValueError('Element-nodal stress record count mismatch')
        maximum=max(float(np.asarray(b.data).max()) for b in fields['S_MISES_MPA'].bulkDataBlocks)
        status={'path':str(path),'nodes':len(p),'elements':len(cells),'stressRecords':count,
            'maximumUnaveragedMisesMPa':maximum,'source':'standalone solver; ODB only for display','readBackVerified':True}
        (directory/'odb_export.json').write_text(json.dumps(status,indent=2),encoding='utf-8');print(json.dumps(status),flush=True)
    finally:check.close()


if __name__=='__main__':export(sys.argv[-1])
