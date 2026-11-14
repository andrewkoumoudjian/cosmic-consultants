"""Unit tests for p0ingest.moon_nuclear (#101). Offline; raw defaults synthetic.

The integration test embeds the real first row of
LPGRS_HIGH1_ELEM_ABUNDANCE_5DEG.TAB with its true byte offsets, so offsets
and decoding stay pinned to the archived bytes without needing the payloads.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import polars as pl

from p0ingest.moon_nuclear import (
    DIAGONAL_1SIGMA,
    EXPECTED_COLS,
    ID_COLUMNS,
    RANGES,
    _check_null_reason,
    _decode,
    expected_column_names,
    parse_fmt,
    parse_label,
    read_table,
)

FMT_COLUMNS = (
    [("PIXEL_INDEX", "ASCII_INTEGER", 10, None), ("MIN_LAT", "ASCII_REAL", 7, "deg"),
     ("MAX_LAT", "ASCII_REAL", 7, "deg"), ("MIN_LON", "ASCII_REAL", 7, "deg"),
     ("MAX_LON", "ASCII_REAL", 7, "deg"), ("AM", "ASCII_REAL", 15, "g/mol"),
     ("NEUTRON_DEN", "ASCII_REAL", 15, "g/cm**3"), ("W_MGO", "ASCII_REAL", 15, None),
     ("W_AL2O3", "ASCII_REAL", 15, None), ("W_SIO2", "ASCII_REAL", 15, None),
     ("W_CAO", "ASCII_REAL", 15, None), ("TIO2", "ASCII_REAL", 15, None),
     ("W_FEO", "ASCII_REAL", 15, None), ("W_K", "ASCII_REAL", 15, None),
     ("W_TH", "ASCII_REAL", 15, None), ("W_U", "ASCII_REAL", 15, None)]
    + [(f"E[{i},{j}]", "ASCII_REAL", 15, None) for i in range(9) for j in range(i, 9)]
)


def synthetic_fmt(blocks) -> str:
    start = 1
    parts = []
    for name, data_type, size, unit in blocks:
        parts.append(f"""  OBJECT                       = COLUMN
    COLUMN_NUMBER              = {len(parts) + 1}
    NAME                       = "{name}"
    DATA_TYPE                  = {data_type}
    START_BYTE                 = {start}
    BYTES                      = {size}
    FORMAT                     = "{data_type[-3:]}{size}"
{f'    UNIT                       = "{unit}"' if unit else ''}
  END_OBJECT                  = COLUMN
""")
        start += size
    return "\n".join(parts)


def synthetic_label(rows: int, record_bytes: int) -> str:
    return f'''PDS_VERSION_ID                = PDS3\r
RECORD_TYPE                   = FIXED_LENGTH\r
RECORD_BYTES                  = {record_bytes}\r
FILE_RECORDS                  = {rows}\r
DATA_SET_ID                   = "LP-L-GRS-5-ELEM-ABUNDANCE-V1.0"\r
PRODUCT_ID                    = "LPGRS_TEST"\r
START_TIME                    = 1998-01-17\r
STOP_TIME                     = 1998-10-07\r
\r
OBJECT                        = TABLE\r
  COLUMNS                     = 61\r
  ROWS                        = {rows}\r
  ^STRUCTURE                  = "LPGRS_ELEM_ABUNDANCE.FMT"\r
END_OBJECT                    = TABLE\r
END\r
'''


def synthetic_row(index: int, overrides: dict[str, str] | None = None) -> bytes:
    """One 880-byte row following the declared widths (61 fields + CRLF)."""
    text = {"PIXEL_INDEX": str(index), "MIN_LAT": "-90.0",
            "MAX_LAT": "-87.5", "MIN_LON": "-180.0",
            "MAX_LON": "180.0", "AM": "2.1609e+001",
            "NEUTRON_DEN": "1.5344e-006", "W_MGO": "7.6213e-002",
            "W_AL2O3": "2.8670e-001", "W_SIO2": "4.4507e-001",
            "W_CAO": "1.5633e-001", "TIO2": "1.6727e-003",
            "W_FEO": "4.9428e-002", "W_K": "4.3389e+002",
            "W_TH": "7.9171e-001", "W_U": "2.1514e-001"}
    for i, (name, *_rest) in enumerate(FMT_COLUMNS[16:]):
        text[name] = f"{1.5e-7 * (i + 1):.4e}"
    for name, value in (overrides or {}).items():
        text[name] = value  # blank or any token overrides the default
    row = b""
    for name, data_type, size, _ in FMT_COLUMNS:
        raw = text[name].encode()
        if data_type == "ASCII_INTEGER":
            row += raw.rjust(size)
        else:
            row += b" " + raw.rjust(size - 1)
    row += b"\r\n"
    assert len(row) == 880, len(row)
    return row


class MoonNuclearLabels(unittest.TestCase):
    def test_label_parsing_quoting_and_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LPGRS_TEST.LBL"
            path.write_text(synthetic_label(rows=3, record_bytes=880))
            label = parse_label(path)
            self.assertEqual(label["recordBytes"], 880)
            self.assertEqual(label["rows"], 3)
            self.assertEqual(label["fileRecords"], 3)
            self.assertEqual(label["columns"], 61)
            self.assertEqual(label["productId"], "LPGRS_TEST")
            self.assertEqual(label["dataSetId"], "LP-L-GRS-5-ELEM-ABUNDANCE-V1.0")
            self.assertEqual(label["startTime"], "1998-01-17")
            self.assertEqual(label["structure"], "LPGRS_ELEM_ABUNDANCE.FMT")
            other = path.read_text().replace("LP-L-GRS-5-ELEM-ABUNDANCE-V1.0",
                                             "OTHER-DATA-SET")
            other_path = Path(directory) / "other.LBL"
            other_path.write_text(other)
            with self.assertRaises(ValueError):
                parse_label(other_path)

    def test_fmt_name_mapping_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LPGRS_ELEM_ABUNDANCE.FMT"
            path.write_text(synthetic_fmt(FMT_COLUMNS))
            columns = parse_fmt(path)
            self.assertEqual(len(columns), 61)
            self.assertEqual([c["name"] for c in columns], expected_column_names())
            self.assertEqual(columns[0]["name"], "pixel_index")
            # E[0,0] -> e0_0; E[8,8] -> e8_8
            self.assertEqual(columns[16]["name"], "e0_0")
            self.assertEqual(columns[-1]["name"], "e8_8")
            self.assertEqual(columns[1]["unit"], "deg")
            self.assertEqual(columns[0]["start0"], 0)
            self.assertEqual(columns[5]["start0"], 38)

    def test_decode_reasons(self):
        column = {"name": "w_feo", "data_type": "ASCII_REAL", "start0": 0, "bytes": 15}
        self.assertEqual(_decode(b"   4.9428e-002   \r\n", column), (0.049428, None))
        self.assertEqual(_decode(b"               \r\n", column), (None, "empty-source-field"))
        self.assertEqual(_decode(b"   not-a-number   \r\n", column), (None, "value-not-numeric"))
        self.assertEqual(_decode(b"        inf       \r\n", column), (None, "non-finite-source-value"))
        integer = {"name": "pixel_index", "data_type": "ASCII_INTEGER", "start0": 0, "bytes": 10}
        self.assertEqual(_decode(b"        17\r\n", integer), (17, None))


class MoonNuclearReadTable(unittest.TestCase):
    def _write_table(self, root: Path, rows: list[bytes], rows_declared: int | None = None):
        fmt_path = root / "LPGRS_ELEM_ABUNDANCE.FMT"
        fmt_path.write_text(synthetic_fmt(FMT_COLUMNS))
        columns = parse_fmt(fmt_path)
        table_path = root / "LPGRS_TEST.TAB"
        table_path.write_bytes(b"".join(rows))
        label_path = root / "LPGRS_TEST.LBL"
        label_path.write_text(synthetic_label(rows_declared or len(rows), record_bytes=880))
        return table_path, label_path, columns

    def test_values_sigmas_and_empty_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table_path, label_path, columns = self._write_table(
                root, [synthetic_row(0), synthetic_row(1)])
            label = parse_label(label_path)
            frame = read_table(table_path, columns, label)
            self.assertEqual(frame.height, 2)
            self.assertEqual(frame["pixel_index"].dtype, pl.UInt32)
            self.assertEqual(frame["pixel_index"].to_list(), [0, 1])
            self.assertAlmostEqual(frame["w_feo"][0], 0.049428, places=9)
            self.assertAlmostEqual(frame["w_th"][1], 0.79171, places=9)
            self.assertAlmostEqual(frame["feo_1sigma_g_g"][0],
                                   math.sqrt(frame["e5_5"][0]), places=12)
            self.assertAlmostEqual(frame["k_1sigma_ppm"][0],
                                   math.sqrt(frame["e6_6"][0]), places=12)
            self.assertAlmostEqual(frame["th_1sigma_ppm"][0],
                                   math.sqrt(frame["e7_7"][0]), places=12)
            # fully-populated rows: empty JSON, null nowhere
            self.assertEqual(json.loads(frame["missing_reason"][0]), {})
            self.assertEqual(_null_count(frame), 0)
            _check_null_reason(frame)  # keys match nulls exactly

    def test_blank_field_nulls_with_reason_and_sigma_inheritance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blank_am = synthetic_row(2, {"AM": ""})
            blank_e55 = synthetic_row(3, {"E[5,5]": ""})
            table_path, label_path, columns = self._write_table(
                root, [blank_am, blank_e55])
            label = parse_label(label_path)
            frame = read_table(table_path, columns, label)
            self.assertIsNone(frame["am"][0])
            self.assertEqual(json.loads(frame["missing_reason"][0]),
                             {"am": "empty-source-field"})
            self.assertIsNone(frame["feo_1sigma_g_g"][1])
            reasons = json.loads(frame["missing_reason"][1])
            self.assertEqual(reasons["e5_5"], "empty-source-field")
            self.assertEqual(reasons["feo_1sigma_g_g"],
                             "source-error-matrix-term-missing")
            self.assertEqual(frame["w_feo"][1], 0.049428)  # other columns intact
            _check_null_reason(frame)

    def test_size_and_delimiter_mismatch_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table_path, label_path, columns = self._write_table(
                root, [synthetic_row(0)])
            with table_path.open("ab") as stream:
                stream.write(b"x")
            with self.assertRaises(ValueError):
                read_table(table_path, columns, parse_label(label_path))
            table_path.write_bytes(synthetic_row(0)[:-2] + b"\n\n")
            with self.assertRaises(ValueError):
                read_table(table_path, columns, parse_label(label_path))

    def test_column_count_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table_path, label_path, columns = self._write_table(
                root, [synthetic_row(0)])
            short = columns[:-1]
            with self.assertRaises(ValueError):
                read_table(table_path, short, parse_label(label_path))


class MoonNuclearConfig(unittest.TestCase):
    def test_expected_names_shape(self):
        names = expected_column_names()
        self.assertEqual(len(names), EXPECTED_COLS)
        self.assertEqual(len(set(names)), EXPECTED_COLS)
        self.assertEqual(names[16:], [f"e{i}_{j}" for i in range(9) for j in range(i, 9)])

    def test_diagonal_terms_and_ranges(self):
        names = set(expected_column_names())
        value_names = names - set(ID_COLUMNS)
        for term, (sigma, unit) in DIAGONAL_1SIGMA.items():
            self.assertIn(term, value_names)
            self.assertNotIn(sigma, names)  # derived by this module, not a source column
            self.assertIn(unit, ("g/g", "ppm"))
        for product, ranges in RANGES.items():
            self.assertLessEqual(set(ranges), value_names)
            self.assertTrue({"am", "neutron_den", "w_feo", "w_k", "w_th"} <= set(ranges))
            for low, high in ranges.values():
                self.assertLess(low, high)
        # the 2-degree product (archive-flagged as poorly evaluated) uses the
        # same or wider bounds than the evaluated 5-degree product
        for column, (low, high) in RANGES["5DEG"].items():
            wide_low, wide_high = RANGES["2DEG"][column]
            self.assertLessEqual(wide_low, low)
            self.assertGreaterEqual(wide_high, high)


REAL_FIRST_ROW = b'         0  -90.0  -87.5 -180.0  180.0    2.1609e+001    1.5344e-006    7.6213e-002    2.8670e-001    4.4507e-001    1.5633e-001    1.6727e-003    4.9428e-002    4.3389e+002    7.9171e-001    2.1514e-001    6.6536e-006    0.0000e+000    0.0000e+000   -1.8852e-006    0.0000e+000    0.0000e+000   -2.2310e-002    1.1900e-007   -2.6756e-006    1.6166e-005    0.0000e+000   -5.0823e-006    0.0000e+000   -1.4726e-006    4.0943e-003   -1.3823e-005    3.9954e-006    1.2188e-005   -4.8501e-007   -3.6164e-007    1.2217e-007    1.5153e-002    1.4800e-005   -2.1926e-005    5.7108e-006    0.0000e+000    0.0000e+000    2.4006e-003   -4.8580e-006    6.6773e-006    1.3902e-007    2.5797e-008   -3.2770e-004    1.9772e-007    1.5387e-006    5.1453e-007    2.9189e-004    6.9154e-007    1.9850e-006    2.4640e+002    0.0000e+000    0.0000e+000    3.3237e-004   -4.8165e-005    1.8968e-004\r\n'


class MoonNuclearRealBytes(unittest.TestCase):
    """The embedded archive row decodes to the expected published values."""

    def test_real_first_row_decodes(self):
        self.assertEqual(len(REAL_FIRST_ROW), 880)
        row = REAL_FIRST_ROW
        widths = {"min_lat": 7, "max_lat": 7, "min_lon": 7, "max_lon": 7}
        columns = [{"name": name, "data_type": "ASCII_INTEGER" if width == 10 else "ASCII_REAL",
                    "start0": start, "bytes": width}
                   for name, start, width in (
                       ("pixel_index", 0, 10), ("min_lat", 10, 7), ("max_lat", 17, 7),
                       ("min_lon", 24, 7), ("max_lon", 31, 7), ("am", 38, 15),
                       ("neutron_den", 53, 15), ("w_feo", 143, 15), ("w_k", 158, 15),
                       ("w_th", 173, 15), ("e5_5", 728, 15), ("e6_6", 788, 15),
                       ("e7_7", 833, 15), ("e8_8", 863, 15))]
        expected = {"pixel_index": 0, "min_lat": -90.0, "max_lat": -87.5,
                    "min_lon": -180.0, "max_lon": 180.0, "am": 21.609,
                    "neutron_den": 1.5344e-06, "w_feo": 0.049428, "w_k": 433.89,
                    "w_th": 0.79171, "e5_5": 5.1453e-07, "e6_6": 2.4640e+02,
                    "e7_7": 3.3237e-04, "e8_8": 1.8968e-04}
        for column in columns:
            got, reason = _decode(row, column)
            self.assertIsNone(reason, column["name"])
            self.assertAlmostEqual(float(got), expected[column["name"]], places=9,
                                   msg=column["name"])
        # south-polar pixel: KREEP-free thorium, published value retained
        self.assertLess(_decode(row, columns[9])[0], 1.0)


def _null_count(frame: pl.DataFrame) -> int:
    return sum(frame[c].null_count() for c in frame.columns if c != "missing_reason")


if __name__ == "__main__":
    unittest.main()
