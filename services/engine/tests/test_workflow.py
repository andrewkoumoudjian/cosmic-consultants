"""Workflow conformance tests; invented fixtures are labelled synthetic."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_engine import synthetic, EXAMPLE, A, B

class StrictBoundaryContract(unittest.TestCase):
    def test_zero_geometric_gap_is_allowed_for_strict_boundary(self):
        from jsonschema import Draft202012Validator
        root = Path(__file__).resolve().parents[3]
        schema = json.loads((root / 'contracts/site-plan.schema.json').read_text())
        validator = Draft202012Validator({'$ref':'#/$defs/monthVerdict', '$defs':schema['$defs']})
        errors = list(validator.iter_errors({'month':1,'value':10,'verdict':'miss','gap':0,'side':'above'}))
        self.assertEqual(errors, [])

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        from planner.publish import load_l3
        self.l3 = load_l3(Path(__file__).resolve().parents[3])
        self.request = copy.deepcopy(EXAMPLE)

    def test_strict_boundary_and_unknown_window(self):
        from planner.workflow import verdict, window_verdict
        self.assertEqual(verdict(10, {'lo':0,'hi':10,'hiStrict':True}), {'verdict':'miss','gap':0,'side':'above'})
        self.assertEqual(verdict(10, {'lo':0,'hi':10}), {'verdict':'match'})
        self.assertEqual(window_verdict([{'verdict':'match'},{'verdict':'unknown','reason':{'code':'missing','text':'missing'}}])['verdict'], 'unknown')
        self.assertEqual(window_verdict([])['verdict'], 'unknown')
        with self.assertRaises(ValueError): verdict(float('nan'), {'lo':0,'hi':10})

    def test_request_priority_missingness_and_tightening(self):
        from planner.workflow import site_plan, search
        tables = synthetic()
        a = site_plan(tables, self.l3, self.request, A)
        self.assertEqual(a['funnelClass'], 'someMiss')  # known slope 6.2 outside must 0..5
        self.request['bandEdits'] = [{'dimension':'terrain','lo':0,'hi':7}]
        a = site_plan(tables, self.l3, self.request, A)
        self.assertEqual(a['funnelClass'], 'noMissSomeUnknown')  # other default must traits still unknown
        self.request['nice'] = ['thermal','dustProcess']
        self.assertEqual(site_plan(tables, self.l3, self.request, A)['funnelClass'], 'allMatch')
        before = search(tables, self.l3, self.request)
        self.assertEqual(before['counts']['matches'], 1)
        self.request['bandEdits'][0]['hi'] = 5
        self.assertEqual(search(tables,self.l3,self.request)['counts']['matches'], 0)
        b = site_plan(tables,self.l3,self.request,B)
        slope = next(r for r in b['verdicts'] if r['dimension']=='terrain')
        self.assertEqual(slope['reason']['text'], 'no-dem-tile')

    def test_banded_rule_without_earth_column_says_no_earth_column(self):
        # #166: a rule with a band but no Earth column is not a per-site data gap.
        from planner.workflow import _rows, NO_EARTH_COLUMN
        tables = synthetic()
        for table in (None, 'L1'):
            rule = {'dimension':'subsurface','table':table,'earthColumn':None,'unit':'m','band':{'lo':0,'hi':1},'origin':'team','priority':'must'}
            row = _rows(tables, self.request, A, rule)
            self.assertEqual((row['verdict'], row['value'], row['reason']), ('unknown', None, NO_EARTH_COLUMN))
            self.assertNotIn('gap', row)
        unbanded = {'dimension':'subsurface','table':None,'earthColumn':None,'unit':None,'band':None,'origin':'target','priority':'must'}
        self.assertEqual(_rows(tables, self.request, A, unbanded)['reason']['code'], 'no-band')  # unchanged for today's SE-3LM rule

    def test_pareto_layers_preserve_ties_and_tradeoffs(self):
        from planner.workflow import pareto_layers
        self.assertEqual(pareto_layers([(0,2),(1,1),(2,0),(2,2),(0,2)]), [1,1,1,2,1])
        self.assertEqual(pareto_layers([(),(),()]), [1,1,1])

    def test_pareto_layers_ignore_unbanded_nice_rules(self):
        from planner.workflow import search
        tables = synthetic()
        # Under OP-5LM, thermal/dustProcess have band=None; terrain has band=[0,5].
        # Site A has slope 6.2 (terrain miss, gap 1.2) and barren 71 (must match);
        # Site B has slope None (missing banded nice rule -> unranked) and barren 40.5 (miss).
        req = {**self.request, "must": ["surfaceMaterial"], "nice": ["terrain", "thermal", "dustProcess"]}
        res = search(tables, self.l3, req)
        self.assertEqual(res["counts"]["matches"], 1)
        self.assertEqual(res["sites"][0]["paretoLayer"], 1)

    def test_schema_and_export_for_synthetic_plan(self):
        from planner.workflow import site_plan, brief
        from referencing import Registry, Resource
        from jsonschema import Draft202012Validator
        root = Path(__file__).resolve().parents[3]
        resources = [json.loads(p.read_text()) for p in (root/'contracts').glob('*.json')]
        registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in resources)
        schema = next(s for s in resources if s['$id'].endswith('/site-plan.schema.json'))
        p = site_plan(synthetic(), self.l3, self.request, A)
        self.assertEqual(list(Draft202012Validator(schema,registry=registry).iter_errors(p)), [])
        text = brief(p)
        self.assertIn('pressureRegime', text)
        self.assertIn('SYNTHETIC', text)
        self.assertIn('not checked', text.lower())

    def test_invalid_or_unavailable_requests_fail_clearly(self):
        from planner.workflow import site_plan
        for change in [{'body':'moon'}, {'months':{'start':0,'end':13}}, {'must':['madeup']}, {'pins':[A,A]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                site_plan(synthetic(),self.l3,{**self.request,**change},A)

class RequestValidationTests(unittest.TestCase):
    def test_invalid_limits_version_and_duplicate_edits_are_rejected(self):
        from planner.workflow import requirements
        from planner.publish import load_l3
        l3=load_l3(Path(__file__).resolve().parents[3])
        for patch in [{'version':2},{'missionType':'teleport'},{'limits':{'access':float('nan')}},{'limits':{'slope':100}},{'top':0},{'surprise':True}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):requirements(l3,{**EXAMPLE,**patch})

class AdditionalInputTests(unittest.TestCase):
    def test_invalid_trip_sort_pins_and_boolean_bounds_are_rejected(self):
        from planner.workflow import requirements
        from planner.publish import load_l3
        l3=load_l3(Path(__file__).resolve().parents[3])
        for patch in [{'durationDays':-1},{'teamSize':0},{'sortBy':'subsurface'},{'pins':['wrong']},{'bandEdits':[{'dimension':'terrain','lo':False,'hi':5}]}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):requirements(l3,{**EXAMPLE,**patch})
