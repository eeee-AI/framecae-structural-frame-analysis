"""Textbook compatibility endpoints backed by the external archive catalog."""
from .archive_layout import catalog as archive_catalog
def _items():return [c for c in archive_catalog()['cases'] if c['id'].startswith(('06_','07_'))]
def catalog():return {'cases':[dict(id='IV1' if c['id'].startswith('06_') else 'IV2',name=c['name']) for c in _items()]}
def detail(case):
    if case not in ('IV1','IV2'):raise ValueError('未知课本算例')
    c=_items()[0 if case=='IV1' else 1]
    return dict(id=case,name=c['name'],model=c['model'],file=c['modelFile'],localTasks=c['tasks'])
def progress():return dict(state='completed',regions=[])
