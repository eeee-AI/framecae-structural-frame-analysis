"""Contain native CAD/mesh failures in a child process."""
import json,sys,traceback
import faulthandler
import contextlib
from pathlib import Path
from .geometry import build

if __name__=='__main__':
    directory=Path(sys.argv[1]).resolve()
    trace=(directory/'geometry_trace.log').open('w',encoding='utf-8',buffering=1)
    faulthandler.enable(file=trace);faulthandler.dump_traceback_later(120,repeat=True,file=trace)
    try:
        request=json.loads((directory/'local_request.json').read_text('utf-8'))
        if request.get('analysisType') in ('continuousPipe','idealClamp'):
            from .line_geometry import build
        with contextlib.redirect_stdout(trace):build(request,directory,request['mesh']['toeSize'],request['mesh']['size'],request['mesh']['focusSize'])
    except BaseException:
        (directory/'geometry_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
