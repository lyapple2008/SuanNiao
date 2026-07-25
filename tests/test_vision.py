import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from suanniao.vision import BoardRecognizer


ROOT = Path(__file__).resolve().parents[1]


class VisionTests(unittest.TestCase):
    def test_reference_screenshot(self) -> None:
        result = BoardRecognizer().read(ROOT / "game.jpg")

        self.assertEqual(len(result.branches), 18)
        self.assertEqual(
            [len(branch.birds) for branch in result.branches],
            [4, 2, 4, 4, 4, 4, 4, 3, 2, 4, 4, 4, 4, 4, 4, 3, 2, 4],
        )
        self.assertEqual(result.state.bird_count, 64)
        self.assertEqual(result.type_count, 7)
        self.assertEqual(sorted(result.cluster_sizes), [8, 8, 8, 8, 8, 12, 12])
        self.assertEqual(sorted(Counter(result.cluster_sizes).values()), [2, 5])

    def test_capacity_constrained_debug_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            debug_dir = Path(directory)
            result = BoardRecognizer(type_count=9).read(
                ROOT / "game.jpg", debug_dir=debug_dir
            )

            self.assertTrue((debug_dir / "index.html").is_file())
            self.assertTrue((debug_dir / "01-detection.png").is_file())
            self.assertTrue((debug_dir / "clusters-k09.png").is_file())
            self.assertEqual(len(list((debug_dir / "birds").glob("bird-*.png"))), 64)
            report = json.loads((debug_dir / "report.json").read_text())
            self.assertEqual(report["detected_birds"], 64)
            self.assertEqual(
                report["clustering_algorithm"], "capacity-constrained-kmeans"
            )
            self.assertEqual(report["candidates"][0]["type_count"], 9)
            self.assertTrue(
                any(
                    size % 4
                    for size in report["candidates"][0]["raw_cluster_sizes"]
                )
            )
            self.assertTrue(report["candidates"][0]["valid"])
            self.assertTrue(all(size % 4 == 0 for size in result.cluster_sizes))


if __name__ == "__main__":
    unittest.main()
