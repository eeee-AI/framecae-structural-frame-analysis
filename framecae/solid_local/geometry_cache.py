"""Reuse geometry only; loads, motions, stresses and validation are recomputed."""
import json,hashlib,shutil,os
from pathlib import Path

def key(q,meta=None):
    mesh=dict(q['mesh'])
    if meta:mesh.update(size=meta['bodySize'],focusSize=meta['focusSize'],toeSize=meta['toeSize'])
    return hashlib.sha256(json.dumps(dict(geometry=q['geometry'],mesh=mesh,
        arms=[{k:a[k] for k in ['element','direction','length','outerRadius','innerRadius']} for a in q['arms']]),sort_keys=True).encode()).hexdigest()

def reuse(directory,request):
    directory=Path(directory);wanted=key(request)
    for other in directory.parent.iterdir():
        if other==directory or not (other/'mesh_meta.json').exists() or not (other/'local_request.json').exists():continue
        try:
            meta=json.loads((other/'mesh_meta.json').read_text('utf-8'));q=json.loads((other/'local_request.json').read_text('utf-8'))
            if meta['minGmshDetJac']<=0 or key(q,meta)!=wanted or not (other/'mesh.npz').exists():continue
        except (ValueError,KeyError,OSError):continue
        for name in ['mesh.npz','mesh_meta.json','geometry.step','mesh.msh']:
            if not (other/name).exists():continue
            # Keep mesh files immutable: hard-link where supported, else copy.
            if (directory/name).exists():continue
            try:os.link(other/name,directory/name)
            except OSError:shutil.copy2(other/name,directory/name)
        return other.name
    return None
