"""Read the verified assembly only; leave source artifacts untouched."""
import json
import math
import struct
from pathlib import Path
from .tables import Tables, sha256_file
from .publish import CELL_COLUMNS, CONTEXT_COLUMNS, MONTHLY_COLUMNS

PHYSICAL=set(CELL_COLUMNS)|set(CONTEXT_COLUMNS)|set(MONTHLY_COLUMNS)

def f32(value):
    if value is None:return None
    if not math.isfinite(value):raise ValueError('Nonfinite source observation')
    result=struct.unpack('<f',struct.pack('<f',float(value)))[0]
    if not math.isfinite(result):raise ValueError('Observation overflows published Float32')
    return result

def from_assembled(root:Path,registry_path:Path|None=None)->Tables:
    import pyarrow.parquet as pq
    root=Path(root)
    report_path=root/'assembly-report.json'
    report=json.loads(report_path.read_text())
    if report['result']!='ALL PASS' or any(not c['pass'] for c in report['checks']) or report['skipped']:
        raise ValueError('Assembly has failed or skipped checks')
    if registry_path is not None and sha256_file(registry_path)!=report['registry']['sha256']:raise ValueError('Assembly registry hash mismatch')
    for name,meta in report['outputs'].items():
        path=root/Path(meta['path']).name
        if not path.exists() or sha256_file(path)!=meta['sha256']:raise ValueError(f'Assembly hash mismatch: {name}')
    inputs=[{'path':'data/snapshots/_derived/assembled/assembly-report.json','sha256':sha256_file(report_path)}]
    def rows(name):
        path=root/(name+'.parquet')
        if not path.exists():return []
        inputs.append({'path':'data/snapshots/_derived/assembled/'+path.name,'sha256':sha256_file(path)})
        frame=pq.read_table(path)
        if name=='sites-r4-monthly':
            frame=frame.select([c for c in frame.column_names if c in set(MONTHLY_COLUMNS)|{'h3','month','missing_reason','burned_pct'}])
        result=frame.to_pylist()
        if len(result)!=report['outputs'][name]['rows']:raise ValueError('Assembly row count changed')
        for r in result:
            for c in PHYSICAL.intersection(r):r[c]=f32(r[c])
        return result
    cell_rows=rows('sites-r4');cells={r['h3']:r for r in cell_rows}
    month_rows=rows('sites-r4-monthly');monthly={(r['h3'],r['month']):r for r in month_rows}
    if not cells or len(cells)!=len(cell_rows):raise ValueError('Empty or duplicate site keys')
    if len(monthly)!=len(month_rows) or len(month_rows)!=len(cells)*12:raise ValueError('Incomplete or duplicate monthly keys')
    if any(h not in cells or m not in range(1,13) for h,m in monthly):raise ValueError('Invalid monthly key domain')
    events={}
    for r in rows('hazard-events'):events.setdefault(r['h3'],[]).append(r)
    return Tables(cells,monthly,cells,events,inputs)
