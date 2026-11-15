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
            self.assertIsNone(tables.cells['84b2203ffffffff']['ati_terra_proxy'])
            self.assertEqual(json.loads(tables.cells['84b2203ffffffff']['missing_reason'])['ati_terra_proxy'],'earth-features-not-in-assembly')
            self.assertEqual(tables.monthly[('84b2203ffffffff',1)]['missing_reason'],'{"lst_day_k":"cloud"}')
            with (root/'sites-r4.parquet').open('ab') as f:f.write(b'x')
            with self.assertRaisesRegex(ValueError,'hash'):from_assembled(root)

    def test_feature_columns_join_by_key_keep_float32_and_column_reasons(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        from planner.assembled import from_assembled
        from planner.publish import publish, read_column, FEATURE_COLUMNS
        keys=['84b2203ffffffff','8429927ffffffff']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            frames={
                'sites-r4':[{'h3':h,'lat':1.0,'lon':2.0,'slope_mean_deg':3.0,
                             'missing_reason':'{"dust_aod_mean":"source-dust-gap"}'} for h in keys],
                'sites-r4-monthly':[{'h3':h,'month':m} for h in keys for m in range(1,13)],
                # Reversed source order catches positional joins. The redundant
                # slope value must never replace the site's existing measurement.
                'earth-features-r4':[
                    {'h3':keys[1],**{c:None for c in FEATURE_COLUMNS},'slope_mean_deg':99.0,
                     'missing_reason':json.dumps({c:'source-gap-'+c for c in FEATURE_COLUMNS})},
                    {'h3':keys[0],**{c:6.2 for c in FEATURE_COLUMNS},'slope_mean_deg':99.0,'missing_reason':'{}'},
                ],
            }
            def write_report():
                outputs={}
                for name,rows in frames.items():
                    p=root/(name+'.parquet');pq.write_table(pa.Table.from_pylist(rows),p)
                    outputs[name]={'path':str(p),'sha256':sha256_file(p),'rows':len(rows)}
                (root/'assembly-report.json').write_text(json.dumps({'result':'ALL PASS','checks':[{'pass':True}],
                    'skipped':[],'outputs':outputs,'inputs':{}}))
            write_report()
            tables=from_assembled(root)
            self.assertEqual(tables.cells[keys[0]]['ati_terra_proxy'],6.199999809265137)
            self.assertEqual(tables.cells[keys[0]]['slope_mean_deg'],3.0)
            self.assertEqual(json.loads(tables.cells[keys[1]]['missing_reason'])['dust_aod_mean'],'source-dust-gap')
            self.assertTrue(any(i['path'].endswith('/earth-features-r4.parquet') for i in tables.inputs))
            out=root/'published';publish(tables,{},out)
            meta=json.loads((out/'yearly/yearly.json').read_text())
            for c in FEATURE_COLUMNS:
                self.assertEqual(meta['nullReasons'][c],{'source-gap-'+c:1})
                self.assertEqual(read_column(out,c)[tables.order().index(keys[0])],6.199999809265137)
                self.assertIsNone(read_column(out,c)[tables.order().index(keys[1])])
            with (root/'earth-features-r4.parquet').open('ab') as f:f.write(b'x')
            with self.assertRaisesRegex(ValueError,'hash'):from_assembled(root)
            # A verified file with wrong/duplicate H3 keys must fail, not align by row.
            frames['earth-features-r4'][0]['h3']=keys[0]
            write_report()
            with self.assertRaisesRegex(ValueError,'feature keys'):from_assembled(root)
