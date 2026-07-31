import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from suanniao.vision import BoardRecognizer


ROOT = Path(__file__).resolve().parents[1]


class VisionTests(unittest.TestCase):
    def test_game_board_check_allows_two_remaining_branches_on_one_side(self) -> None:
        recognizer = BoardRecognizer()
        screenshot = Image.new("RGB", (100, 200), "black")

        with patch.object(
            recognizer,
            "_detect_branch_rows",
            return_value={"left": [80, 120], "right": []},
        ):
            self.assertTrue(recognizer.has_game_board(screenshot))

        with patch.object(
            recognizer,
            "_detect_branch_rows",
            return_value={"left": [], "right": []},
        ):
            self.assertFalse(recognizer.has_game_board(screenshot))

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
            self.assertEqual(
                len(list((debug_dir / "feature-masks").glob("bird-*.png"))),
                64,
            )
            report = json.loads((debug_dir / "report.json").read_text())
            self.assertEqual(report["detected_birds"], 64)
            self.assertEqual(
                report["clustering_algorithm"], "capacity-constrained-kmeans"
            )
            self.assertEqual(
                report["occupancy_constraint"],
                "prefix-per-branch,total-multiple-of-capacity",
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

    def test_global_occupancy_constraint_removes_marginal_extra_bird(self) -> None:
        recognizer = BoardRecognizer(presence_threshold=0.20)

        occupancies = recognizer._select_occupancies(
            (
                (0.8, 0.8, 0.8, 0.8),
                (0.201, 0.1, 0.1, 0.1),
            )
        )

        self.assertEqual(occupancies, (4, 0))

    def test_presence_evidence_rejects_thin_wood_strip(self) -> None:
        rgb = np.full((1478, 680, 3), (155, 215, 240), dtype=np.uint8)
        x, y = 50, 600
        rgb[y - 32 : y - 24, x - 20 : x + 20] = (125, 65, 30)

        evidence = BoardRecognizer()._presence_evidence(rgb, x, y)

        self.assertLess(evidence.score, 0.20)
        self.assertGreater(evidence.foreground_fraction, evidence.bird_fraction)

    def test_edge_crop_uses_background_instead_of_black_padding(self) -> None:
        color = (155, 215, 240)
        image = Image.new("RGB", (100, 200), color)
        background = np.asarray(color, dtype=float) / 255.0

        crop = BoardRecognizer._bird_crop(
            image,
            0,
            80,
            "left",
            image.width,
            image.height,
            background,
            has_outer_neighbor=False,
        )

        self.assertEqual(crop.getextrema(), ((155, 155), (215, 215), (240, 240)))

    def test_bird_crop_boxes_shift_toward_screen_center(self) -> None:
        left_box = BoardRecognizer._bird_crop_box(
            100,
            200,
            "left",
            1000,
            2000,
            has_outer_neighbor=True,
        )
        right_box = BoardRecognizer._bird_crop_box(
            900,
            200,
            "right",
            1000,
            2000,
            has_outer_neighbor=True,
        )

        self.assertGreater(left_box[0] + left_box[2], 2 * 100)
        self.assertLess(right_box[0] + right_box[2], 2 * 900)

    def test_screen_edge_crop_boxes_are_moved_fully_inside_image(self) -> None:
        left_box = BoardRecognizer._bird_crop_box(
            32,
            200,
            "left",
            1000,
            2000,
            has_outer_neighbor=True,
        )
        right_box = BoardRecognizer._bird_crop_box(
            968,
            200,
            "right",
            1000,
            2000,
            has_outer_neighbor=True,
        )

        self.assertEqual(left_box[0], 0)
        self.assertEqual(right_box[2], 1000)

    def test_bird_feature_mask_favors_base_side_over_outer_neighbor(self) -> None:
        background = np.asarray((155, 215, 240), dtype=float) / 255.0
        pixels = np.full((62, 49, 3), (155, 215, 240), dtype=np.uint8)
        # After right-side normalization, the target bird's base-side body is
        # on the left and contamination from the outer neighbor is on the right.
        pixels[20:40, 8:17] = (30, 30, 30)
        pixels[20:40, 37:46] = (30, 30, 30)

        mask = BoardRecognizer._bird_feature_mask(
            Image.fromarray(pixels), background
        )

        self.assertTrue(mask[28, 12])
        self.assertFalse(mask[28, 41])

    def test_capacity_targets_use_visual_cost_to_break_size_tie(self) -> None:
        recognizer = BoardRecognizer()
        matrix = np.asarray([[0.0]] * 8 + [[10.0]] * 12)
        centers = np.asarray([[0.0], [10.0]])

        targets = recognizer._capacity_targets(matrix, centers, (6, 14))

        # (4, 16) and (8, 12) change the raw sizes by the same amount, but
        # the visual assignment clearly supports eight samples at center 0.
        self.assertEqual(targets, (8, 12))


if __name__ == "__main__":
    unittest.main()
