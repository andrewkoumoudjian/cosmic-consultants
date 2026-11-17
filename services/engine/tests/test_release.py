"""Release boundary checks: assumptions, error visibility, and split measurements."""
import copy
import hashlib
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator, ValidationError
from planner.release import release
from planner.publish import publish, read_column
from test_engine import synthetic, A

REPO = Path(__file__).resolve().parents[3]


class ReleaseTests(unittest.TestCase):
    def test_feature_arrays_are_lazy_hashed_and_keep_nan_and_proxy_notes(self):
        from planner.publish import FEATURE_COLUMNS
        from test_engine import B
        tables=synthetic()
        values={'ati_terra_proxy':0.03125,'ati_aqua_proxy':0.0,
                'daylight_h_min':0.0,'daylight_h_mean':12.5,'daylight_h_max':24.0}
        for name,v in values.items():
            tables.cells[A][name]=v
            tables.cells[B][name]=None
        tables.cells[B]['missing_reason']=json.dumps({name:'missing-'+name for name in values})
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            manifest=publish(tables,{},out)
            startup=json.loads((out/'cells.json').read_text())
            extra=json.loads((out/'yearly/yearly.json').read_text(encoding='utf-8'))
            self.assertEqual((out/'cells.bin').stat().st_size,len(tables.cells)*26*4)
            for name in FEATURE_COLUMNS:
                self.assertNotIn(name,[c['name'] for c in startup['columns']])
                path='yearly/'+name+'.bin'
                raw=(out/path).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest['files'][path])
                decoded=struct.unpack('<'+'f'*len(tables.cells),raw)
                self.assertEqual(decoded[tables.order().index(A)],values[name])
                self.assertTrue(math.isnan(decoded[tables.order().index(B)]))
                self.assertEqual(extra['nullReasons'][name],{'missing-'+name:1})
            self.assertIn('apparent thermal inertia proxy, (1 − albedo) / diurnal range',extra['columnNotes']['ati_terra_proxy'])
            first=(out/'build-manifest.json').read_bytes()
            publish(tables,{},out)
            self.assertEqual((out/'build-manifest.json').read_bytes(),first)

    def test_examples_require_origin_and_basis_for_every_parameter(self):
        config = yaml.safe_load((REPO/'data/pipeline/release-scenarios.yaml').read_text())
        validator = Draft202012Validator(json.loads((REPO/'contracts/release-scenarios.schema.json').read_text()))
        validator.validate(config)
        bad = copy.deepcopy(config)
        del bad['scenarios'][0]['parameters']['thermalBandK']['origin']
        with self.assertRaises(ValidationError):validator.validate(bad)

    def test_extra_yearly_values_roundtrip_without_increasing_startup_arrays(self):
        tables = synthetic()
        tables.cells[A]['regolith_thick_m'] = 3.25
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            manifest = publish(tables, {'objectives':[], 'trait-map':{}, 'campaigns':[]}, out)
            meta = json.loads((out/'cells.json').read_text())
            self.assertNotIn('regolith_thick_m', [c['name'] for c in meta['columns']])
            self.assertLessEqual(len(meta['columns']), 26)
            self.assertIn('yearly/regolith_thick_m.bin', manifest['files'])
            self.assertEqual(read_column(out, 'regolith_thick_m')[meta['h3'].index(A)], 3.25)

    def test_failed_campaign_is_visible_in_release_summary(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            root = Path(d); assembled = root/'assembled'; assembled.mkdir()
            (assembled/'assembly-report.json').write_text(json.dumps({'inputs':{}}))
            for name in ('planetary-targets.parquet','earth-features-r4.parquet'):
                (assembled/name).write_bytes(b'test')
            (root/'cells-r4-monthly-years.parquet').write_bytes(b'test')
            stack.enter_context(patch('planner.release.from_assembled', return_value=synthetic()))
            stack.enter_context(patch('planner.pareto_model.load_assembled_targets',return_value=[{'target_id':'mars-landing-perseverance'}]))
            rank = stack.enter_context(patch('planner.pareto_model.rank_earth_for_target',return_value={'body':'mars','axes':[], 'notTestableOnEarth':[], 'counts':{}, 'excludedLimits':[]}))
            stack.enter_context(patch('planner.pareto_model.select_diverse_frontier_candidates',return_value=[{'h3':A}]))
            stack.enter_context(patch('planner.optimizer.build_campaign_problem_from_years',return_value=(object(),[])))
            stack.enter_context(patch('planner.optimizer.solve_cvar_campaign',side_effect=ValueError('test infeasible campaign')))
            out=root/'out'
            summary=release(assembled,out,REPO)
            self.assertEqual(summary['campaignErrorCount'],1)
            self.assertIn('test infeasible campaign',summary['campaignErrors'][0]['error'])
            target=json.loads((out/'pareto-targets.json').read_text())['targets']['mars-landing-perseverance']
            self.assertEqual(target['scenarioStatus'],'illustrative-team-assumptions')
            self.assertEqual(target['campaignPlan']['status'],'error')
            self.assertEqual(rank.call_args.kwargs['min_land_pct'],50)
            self.assertEqual(target['parameters']['minLandPct']['origin'],'team')
