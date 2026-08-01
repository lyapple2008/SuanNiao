import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from suanniao.vision import BoardRecognizer, _PresenceEvidence


ROOT = Path(__file__).resolve().parents[1]


class VisionTests(unittest.TestCase):
    def test_game_board_check_allows_two_remaining_branches_on_one_side(self) -> None:
        recognizer = BoardRecognizer()
        screenshot = Image.new("RGB", (100, 200), (163, 219, 254))

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

    def test_game_board_check_rejects_dimmed_modal_overlay(self) -> None:
        recognizer = BoardRecognizer()
        screenshot = Image.new("RGB", (100, 200), (49, 66, 76))

        with patch.object(
            recognizer,
            "_detect_branch_rows",
            return_value={"left": [80], "right": [120]},
        ) as detect_rows:
            self.assertFalse(recognizer.has_game_board(screenshot))

        detect_rows.assert_not_called()

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
                "two-cluster-presence,prefix-per-branch,total-capacity-multiple",
            )
            self.assertEqual(
                report["presence_clustering"]["method"],
                "two-cluster-presence",
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

    def test_presence_clustering_rejects_vines_on_empty_branches(self) -> None:
        recognizer = BoardRecognizer(presence_threshold=0.20)
        bird = _PresenceEvidence(0.68, 0.71, 0.64, 0.62, 0.86, 0.74)
        empty_rows = (
            (
                _PresenceEvidence(0.244, 0.31, 0.244, 0.242, 0.772, 0.31),
                _PresenceEvidence(0.142, 0.18, 0.115, 0.115, 0.570, 0.20),
                _PresenceEvidence(0.015, 0.02, 0.012, 0.012, 0.025, 0.65),
                _PresenceEvidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ),
            (
                _PresenceEvidence(0.183, 0.22, 0.181, 0.180, 0.519, 0.37),
                _PresenceEvidence(0.019, 0.03, 0.017, 0.013, 0.051, 0.60),
                _PresenceEvidence(0.017, 0.02, 0.008, 0.008, 0.063, 0.65),
                _PresenceEvidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ),
        )

        selection = recognizer._select_occupancies(
            ((bird,) * 4, (bird,) * 4, *empty_rows)
        )

        self.assertEqual(selection.method, "two-cluster-presence")
        self.assertEqual(selection.occupancies, (4, 4, 0, 0))

    def test_presence_clustering_rejects_sparse_single_slot_vine(self) -> None:
        recognizer = BoardRecognizer(presence_threshold=0.20)
        bird = _PresenceEvidence(0.62, 0.70, 0.60, 0.57, 0.84, 0.72)
        vine_branch = (
            _PresenceEvidence(0.247, 0.357, 0.248, 0.246, 0.797, 0.308),
            _PresenceEvidence(0.143, 0.207, 0.117, 0.116, 0.595, 0.196),
            _PresenceEvidence(0.029, 0.027, 0.027, 0.027, 0.051, 0.648),
            _PresenceEvidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )

        selection = recognizer._select_occupancies(
            ((bird,) * 4, (bird,) * 4, vine_branch)
        )

        self.assertEqual(selection.occupancies, (4, 4, 0))

    def test_presence_clustering_rejects_fallen_leaf_in_outer_slot(self) -> None:
        recognizer = BoardRecognizer(presence_threshold=0.20)
        bird = _PresenceEvidence(
            0.7415,
            0.8224,
            0.7522,
            0.7289,
            0.9498,
            0.7668,
        )
        empty = _PresenceEvidence(
            0.0012,
            0.0005,
            0.0005,
            0.0005,
            0.0054,
            0.1020,
        )
        fallen_leaf = _PresenceEvidence(
            0.365293,
            0.335849,
            0.335849,
            0.335849,
            0.792453,
            0.609589,
        )
        expected = (3, 2, 3, 3, 3, 4, 2, 4, 4, 4)
        rows = tuple(
            tuple(
                fallen_leaf if branch_index == 0 and slot_index == 3 else bird
                if slot_index < occupied
                else empty
                for slot_index in range(4)
            )
            for branch_index, occupied in enumerate(expected)
        )

        selection = recognizer._select_occupancies(rows)

        self.assertEqual(selection.occupancies, expected)
        self.assertEqual(sum(selection.occupancies) % recognizer.capacity, 0)

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

    def test_layout_scale_tracks_same_side_branch_spacing(self) -> None:
        recognizer = BoardRecognizer()

        normal = recognizer._layout_scale(
            {"left": [835, 958, 1081], "right": [897, 1020, 1143]},
            2622,
        )
        enlarged = recognizer._layout_scale(
            {"left": [845, 998, 1151], "right": [921, 1075, 1229]},
            2622,
        )

        self.assertAlmostEqual(normal, 1.0, places=2)
        self.assertAlmostEqual(enlarged, 1.25, places=2)

    def test_branch_bounds_follow_edge_component_within_half_screen(self) -> None:
        rgb = np.full((300, 1200, 3), (155, 215, 240), dtype=np.uint8)
        branch_y = 150
        wood = (125, 65, 30)
        rgb[branch_y - 4 : branch_y + 5, 0:491] = wood
        rgb[branch_y - 4 : branch_y + 5, 520:571] = wood
        rgb[branch_y - 4 : branch_y + 5, 710:1200] = wood
        rgb[branch_y - 4 : branch_y + 5, 630:681] = wood

        left = BoardRecognizer._branch_x_bounds(rgb, "left", branch_y)
        right = BoardRecognizer._branch_x_bounds(rgb, "right", branch_y)

        self.assertEqual(left, (0, 490))
        self.assertEqual(right, (710, 1199))
        self.assertLess(left[1] - left[0], rgb.shape[1] / 2)
        self.assertLess(right[1] - right[0], rgb.shape[1] / 2)

    def test_branch_slots_use_average_length_and_segment_centers(self) -> None:
        recognizer = BoardRecognizer()
        average_length = recognizer._average_branch_length(
            ((0, 300), (700, 1000), (5, 325)),
            1000,
        )

        left_slots = recognizer._slot_centers(
            "left",
            800,
            1000,
            branch_bounds=(0, 300),
            branch_length=average_length,
        )
        right_slots = recognizer._slot_centers(
            "right",
            800,
            1000,
            branch_bounds=(700, 1000),
            branch_length=average_length,
        )

        self.assertAlmostEqual(average_length, (300 + 300 + 320) / 3)
        self.assertEqual(
            [point[0] for point in left_slots],
            [38, 115, 192, 268],
        )
        self.assertEqual(
            [point[0] for point in right_slots],
            [962, 885, 808, 732],
        )

    def test_layout_scale_expands_crop_size(self) -> None:
        recognizer = BoardRecognizer()
        normal_box = recognizer._bird_crop_box(
            200,
            800,
            "left",
            1206,
            2622,
            has_outer_neighbor=True,
        )
        enlarged_box = recognizer._bird_crop_box(
            200,
            800,
            "left",
            1206,
            2622,
            has_outer_neighbor=True,
            scale=1.25,
        )

        self.assertGreater(
            enlarged_box[2] - enlarged_box[0], normal_box[2] - normal_box[0]
        )
        self.assertGreater(
            enlarged_box[3] - enlarged_box[1], normal_box[3] - normal_box[1]
        )

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
