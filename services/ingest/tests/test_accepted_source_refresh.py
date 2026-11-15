import unittest
import polars as pl
import yaml
from p0ingest.assemble import Build, REPO, normalize_frame


class AcceptedSourceRefresh(unittest.TestCase):
    def test_delivered_dust_is_required_when_its_source_is_missing(self):
        registry = yaml.safe_load((REPO / 'data/pipeline/columns.yaml').read_text())
        column = next(c for c in registry['tables']['sites-r4']['columns'] if c['name'] == 'dust_aod_mean')
        build = object.__new__(Build)
        base = {'name': 'lat', 'from': 'base.lat', 'trait': None, 'unit': 'deg', 'status': 'active'}
        build.reg = {'tables': {'probe': {'key': ['h3'], 'columns': [base, column]}}}
        build.master = pl.DataFrame({'h3': ['a'], 'cell': [0]})
        build.report = {'checks': [], 'skipped': []}
        build.fails = 0
        build.source = lambda source: pl.DataFrame({'h3': ['a'], 'lat': [1.0], 'missing_reason': ['{}']}) if source == 'base' else None
        build.table('probe')
        self.assertGreater(build.fails, 0)
        self.assertEqual(build.report['skipped'], [])

    def test_source_diagnostics_remain_native_with_nonzero_iqr(self):
        build = object.__new__(Build)
        build.reg = {'tables': {'probe': {'columns': [
            {'name': 'aod', 'trait': 'dustProcess', 'unit': '1'},
            {'name': 'months_used', 'trait': None, 'unit': 'count', 'role': 'diagnostic'}]}}}
        frame = pl.DataFrame({'h3': ['a', 'b', 'c', 'd'], 'aod': [0.1, 0.2, 0.3, None],
                              'months_used': [1, 3, 12, None]})
        scales = build.table_scales('probe', frame)
        normalized, info = normalize_frame(frame, scales)
        self.assertEqual(normalized['months_used'].to_list(), frame['months_used'].to_list())
        self.assertEqual(info['scaledColumns'], ['aod'])
        self.assertEqual(info['unscaledColumns']['months_used'], 'source-diagnostic')
        self.assertFalse(scales['months_used']['inSum'])

    def test_latest_document_menu_and_required_support_fields(self):
        catalog = yaml.safe_load((REPO / 'data/pipeline/test-categories.yaml').read_text())
        rows = {r['categoryId']: r for r in catalog['categories']}
        self.assertEqual(len(rows), 19)
        self.assertEqual(catalog['selection']['maxMetrics'], 8)
        self.assertEqual(len(rows['geological-exploration-sampling']['detailedMetricMenuText']), 8)
        self.assertIn('carbonate indicators (proxy)', rows['geological-exploration-sampling']['detailedMetricMenuText'])
        registry = yaml.safe_load((REPO / 'data/pipeline/columns.yaml').read_text())
        columns = {c['name']: c for table in registry['tables'].values() for c in table['columns']}
        for name in ['dust_months_used', 'dust_aod_max_month', 'burned_years_mapped',
                     'regolith_support_frac', 'soil_support_frac']:
            self.assertEqual(columns[name]['role'], 'diagnostic')
            self.assertEqual(columns[name]['status'], 'active')


if __name__ == '__main__':
    unittest.main()
