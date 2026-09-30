import tempfile
import unittest
from pathlib import Path

from src.analysis import summarize_curve
from src.file_manager import read_rodeostat_rows, save_voltammogram_csv
from src.measurement import prepare_device_parameters


class FakePotentiostat:
    def __init__(self):
        self.sample_period = None
        self.current_range = None

    def set_sample_period(self, sample_period):
        self.sample_period = sample_period
        return sample_period

    def set_curr_range(self, current_range):
        self.current_range = current_range
        return current_range


class DataHelperTest(unittest.TestCase):
    def test_save_and_read_rodeostat_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data.csv"

            save_voltammogram_csv(
                output,
                time_s=[0.0, 1.0],
                potential_v=[-0.1, 0.1],
                current=[1.2, 1.3],
            )
            rows = read_rodeostat_rows(output)

            self.assertEqual(rows, [(0.0, -0.1, 1.2), (1.0, 0.1, 1.3)])

    def test_summarize_curve_extracts_peak_values(self):
        summary = summarize_curve(
            channel=1,
            potential=[-0.2, 0.0, 0.2],
            current=[-1.0, 0.5, 2.0],
        )

        self.assertEqual(summary.channel, 1)
        self.assertEqual(summary.max_current, 2.0)
        self.assertEqual(summary.max_current_potential, 0.2)
        self.assertEqual(summary.min_current, -1.0)
        self.assertEqual(summary.min_current_potential, -0.2)

    def test_summarize_curve_prefers_reduction_valley_over_edge_minimum(self):
        summary = summarize_curve(
            channel=1,
            potential=[-0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4],
            current=[-100.0, -55.0, -42.0, -50.0, -62.0, -57.0, -30.0, 5.0, 45.0, 70.0],
        )

        self.assertEqual(summary.min_current, -62.0)
        self.assertEqual(summary.min_current_potential, -0.1)

    def test_summarize_curve_prefers_oxidation_hill_over_edge_maximum(self):
        summary = summarize_curve(
            channel=1,
            potential=[-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4],
            current=[20.0, 35.0, 55.0, 68.0, 60.0, 30.0, 15.0, 50.0, 90.0],
        )

        self.assertEqual(summary.max_current, 68.0)
        self.assertEqual(summary.max_current_potential, -0.1)

    def test_cv_parameters_are_mapped_to_rodeostat_firmware_names(self):
        fake = FakePotentiostat()

        result = prepare_device_parameters(
            fake,
            "cyclic",
            {
                "currentRange": "1000 uA",
                "sampleRate": 50,
                "quietTime": 0,
                "quietValue": -0.5,
                "startValue": -0.5,
                "vertex1Value": 0.5,
                "scanRate": 0.02,
                "numCycles": 3,
            },
        )

        self.assertEqual(fake.current_range, "1000uA")
        self.assertEqual(fake.sample_period, 20)
        self.assertEqual(result["amplitude"], 0.5)
        self.assertEqual(result["offset"], 0.0)
        self.assertEqual(result["period"], 100000)
        self.assertEqual(result["numCycles"], 3)

    def test_non_cv_parameters_are_prepared_for_rodeostat_firmware(self):
        fake = FakePotentiostat()

        result = prepare_device_parameters(
            fake,
            "chronoamp",
            {
                "currentRange": "100 uA",
                "sampleRate": 25,
                "quietTime": "1000",
                "quietValue": "0.0",
                "step": "1000:-0.25,10000:0.5",
            },
        )

        self.assertEqual(fake.current_range, "100uA")
        self.assertEqual(fake.sample_period, 40)
        self.assertNotIn("currentRange", result)
        self.assertNotIn("sampleRate", result)
        self.assertEqual(result["quietTime"], 1000)
        self.assertEqual(result["step"], [(1000, -0.25), (10000, 0.5)])


if __name__ == "__main__":
    unittest.main()
