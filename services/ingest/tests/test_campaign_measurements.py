import unittest
from p0ingest.campaign_measurements import extract_arads


class HistoricalMeasurements(unittest.TestCase):
    def test_achieved_values_and_exact_source_span(self):
        quote = 'The deepest sample that was acquired with fully remote operations required 55 command cycles to drill to 80\u2009cm depth with sample collection and delivery to 3 instruments.'
        text = 'Our field work was performed in September 2019.\n' + quote
        rows = extract_arads(text)
        self.assertEqual([r['value'] for r in rows], [55, 80, 3])
        self.assertEqual([r['unit'] for r in rows], ['command cycles', 'cm', 'instruments'])
        for row in rows:
            self.assertEqual(text[row['source_char_start']:row['source_char_end']], quote)
            self.assertEqual(row['evidence_role'], 'achieved result')
            self.assertIsNone(row['test_date_day'])
            self.assertFalse(row['is_universal_requirement'])

    def test_absent_or_ambiguous_passage_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_arads('drill reached some depth')
        text = 'Our field work was performed in September 2019. The deepest sample that was acquired with fully remote operations required 55 command cycles to drill to 80 cm depth with sample collection and delivery to 3 instruments.'
        with self.assertRaises(ValueError):
            extract_arads(text + text)


if __name__ == '__main__':
    unittest.main()
