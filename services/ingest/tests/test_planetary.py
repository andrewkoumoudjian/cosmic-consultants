import tempfile
import unittest
from pathlib import Path

import numpy as np

from p0ingest.planetary import read_character_label, character_batches, read_tes_image, clean_tes


class PlanetarySources(unittest.TestCase):
    def test_fixed_width_offsets_and_declared_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "x.xml"
            label.write_text('''<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
              <File_Area_Observational><File><file_name>x.tab</file_name></File>
              <Table_Character><offset>8</offset><records>2</records>
              <record_delimiter>Carriage-Return Line-Feed</record_delimiter><Record_Character>
              <fields>2</fields><record_length>12</record_length>
              <Field_Character><name>temp_max</name><field_location>1</field_location><field_length>4</field_length><data_type>ASCII_Real</data_type><unit>Kelvin</unit><description>Surface maximum</description></Field_Character>
              <Field_Character><name>ice_depth</name><field_location>6</field_location><field_length>5</field_length><data_type>ASCII_Real</data_type><unit>meter</unit><description>Model depth</description><Special_Constants><invalid_constant>-999</invalid_constant></Special_Constants></Field_Character>
              </Record_Character></Table_Character></File_Area_Observational></Product_Observational>''')
            (root / "x.tab").write_bytes(b"header\r\n" + b" 120 0.000\r\n" + b" 250  -999\r\n")
            spec = read_character_label(label)
            frames = list(character_batches(root / "x.tab", spec, batch_size=1))
            self.assertEqual(frames[0]["ice_depth"].to_list(), [0.0])
            self.assertEqual(frames[1]["ice_depth"].to_list(), [None])
            self.assertEqual(frames[1]["temp_max"].to_list(), [250.0])
            self.assertEqual(frames[1]["source_record"].to_list(), [1])
            self.assertEqual(frames[1]["ice_depth_source_value"].to_list(), [-999.0])
            self.assertEqual(spec["fields"][0]["unit"], "Kelvin")
            with (root / "x.tab").open("ab") as stream:
                stream.write(b"bad")
            with self.assertRaises(ValueError):
                list(character_batches(root / "x.tab", spec))

    def test_tes_endian_mask_and_outside_computed_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "x.lbl"
            label.write_text('''PDS_VERSION_ID = PDS3
DATA_SET_ID = "MGS-M-TES-5-TIMAP-V1.0"
OBJECT = IMAGE
LINES = 2
LINE_SAMPLES = 3
SAMPLE_TYPE = MSB_INTEGER
SAMPLE_BITS = 16
END_OBJECT = IMAGE
END''')
            values = np.array([[300, 500, 0], [5000, 5001, 5]], dtype=">i2")
            (root / "x.img").write_bytes(values.tobytes())
            result = read_tes_image(root / "x.img", label)
            self.assertEqual(int(result[0, 0]), 300)
            mask = np.array([[1, 0, 1], [1, 1, 1]], dtype=np.uint8)
            frame = clean_tes(result, mask, start_line=7)
            self.assertEqual(frame["thermal_inertia"].to_list(), [300, None, None, 5000, None, 5])
            self.assertEqual(frame["missing_reason"][1], "source-interpolated")
            self.assertEqual(frame["source_line"].to_list(), [7, 7, 7, 8, 8, 8])
            mask[0, 0] = 2
            with self.assertRaises(ValueError):
                clean_tes(result, mask)
            (root / "x.img").write_bytes(b"short")
            with self.assertRaises(ValueError):
                read_tes_image(root / "x.img", label)


if __name__ == "__main__":
    unittest.main()
