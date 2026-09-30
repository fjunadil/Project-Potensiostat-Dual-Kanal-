import tempfile
import unittest
from pathlib import Path

from src.plotter import plot_multiple_voltammograms, plot_voltammogram


class PlotterTest(unittest.TestCase):
    def test_plot_voltammogram_saves_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "cv.png"

            saved = plot_voltammogram(
                potential=[-0.1, 0.0, 0.1],
                current=[1.0, 2.0, 1.5],
                output_path=output,
                show=False,
            )

            self.assertEqual(saved, output)
            self.assertTrue(output.exists())

    def test_plot_multiple_voltammograms_saves_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "multi.png"

            saved = plot_multiple_voltammograms(
                curves=[
                    ([-0.1, 0.0, 0.1], [1.0, 2.0, 1.5], "Channel 1"),
                    ([-0.1, 0.0, 0.1], [0.8, 1.6, 1.2], "Channel 2"),
                ],
                output_path=output,
                show=False,
            )

            self.assertEqual(saved, output)
            self.assertTrue(output.exists())

    def test_plot_multiple_voltammograms_saves_peak_annotations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "multi_with_peaks.png"

            saved = plot_multiple_voltammograms(
                curves=[
                    ([-0.1, 0.0, 0.1], [1.0, 2.0, 1.5], "Channel 1"),
                    ([-0.1, 0.0, 0.1], [0.8, -2.2, 1.2], "Channel 2"),
                ],
                peaks=[
                    (1, 0.0, 2.0, "Oksidasi"),
                    (2, 0.0, -2.2, "Reduksi"),
                ],
                output_path=output,
                show=False,
            )

            self.assertEqual(saved, output)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
