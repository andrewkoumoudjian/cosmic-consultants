import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from planner.tables import sha256_file
class AssemblyTests(unittest.TestCase):
    def test_verified_inputs_retain_missing_reasons_and_use_published_precision(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        from planner.assembled import from_assembled
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            frames={'sites-r4':[{'h3':'84b2203ffffffff','lat':-24.45,'lon':-69.31,'slope_mean_deg':6.2,'missing_reason':'{}'}],
                    'sites-r4-monthly':[{'h3':'84b2203ffffffff','month':m,'lst_day_k':None,'missing_reason':'{"lst_day_k":"cloud"}'} for m in range(1,13)]}
            outputs={}
            for name,rows in frames.items():
                p=root/(name+'.parquet');pq.write_table(pa.Table.from_pylist(rows),p)
                outputs[name]={'path':str(p),'sha256':sha256_file(p),'rows':len(rows)}
            report={'result':'ALL PASS','checks':[{'pass':True}],'skipped':[],'outputs':outputs,'inputs':{}}
            p=root/'assembly-report.json';p.write_text(json.dumps(report))
            tables=from_assembled(root)
            self.assertEqual(tables.cells['84b2203ffffffff']['slope_mean_deg'],6.199999809265137)
            self.assertEqual(tables.monthly[('84b2203ffffffff',1)]['missing_reason'],'{"lst_day_k":"cloud"}')
            with (root/'sites-r4.parquet').open('ab') as f:f.write(b'x')
            with self.assertRaisesRegex(ValueError,'hash'):from_assembled(root)
