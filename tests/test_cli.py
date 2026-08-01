import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from suanniao.cli import (
    _capture_game_board,
    _create_run_directory,
    _destination_click_point,
    _physical_state_key,
    analyze,
    build_parser,
    play,
)
from suanniao.model import BoardState, Move
from suanniao.solver import SolveResult
from suanniao.vision import DetectedBranch, RecognitionResult


def solid_image(color: str) -> Image.Image:
    return Image.new("RGB", (100, 200), color)


class FakeController:
    def __init__(
        self,
        *,
        stable_screenshots: tuple[Image.Image, ...] = (),
        quick_screenshots: tuple[Image.Image, ...] = (),
        dismiss_results: tuple[bool, ...] = (),
    ) -> None:
        self.stable_screenshots = list(stable_screenshots or (solid_image("white"),))
        self.quick_screenshots = list(quick_screenshots or (solid_image("white"),))
        self.dismiss_results = list(dismiss_results)
        self.stable_capture_options: list[dict[str, object]] = []
        self.dismiss_calls = 0
        self.taps: list[tuple[int, int]] = []
        self.closed = False
        self.clear_selection_calls: list[tuple[int, int]] = []

    @staticmethod
    def _next(items: list[Image.Image]) -> Image.Image:
        if len(items) > 1:
            return items.pop(0)
        return items[0]

    def capture_stable(self, **kwargs: object) -> Image.Image:
        self.stable_capture_options.append(kwargs)
        return self._next(self.stable_screenshots)

    def capture(self) -> Image.Image:
        return self._next(self.quick_screenshots)

    def dismiss_interruption(self) -> bool:
        self.dismiss_calls += 1
        if self.dismiss_results:
            return self.dismiss_results.pop(0)
        return False

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def tap_pair(
        self,
        source: tuple[int, int],
        destination: tuple[int, int],
        _gap: float,
    ) -> None:
        self.taps.extend((source, destination))

    def clear_selection(self, image_size: tuple[int, int]) -> None:
        self.clear_selection_calls.append(image_size)

    def close(self) -> None:
        self.closed = True


class FakeRecognizer:
    def __init__(
        self,
        results: RecognitionResult | tuple[RecognitionResult, ...],
        *,
        board_results: tuple[bool, ...] = (True,),
    ) -> None:
        self.results = list(results if isinstance(results, tuple) else (results,))
        self.board_results = list(board_results)
        self.debug_directories: list[Path] = []

    def has_game_board(self, _screenshot: Image.Image) -> bool:
        if len(self.board_results) > 1:
            return self.board_results.pop(0)
        return self.board_results[0]

    def read(
        self, _screenshot: Image.Image, *, debug_dir: Path | None = None
    ) -> RecognitionResult:
        if debug_dir is not None:
            self.debug_directories.append(debug_dir)
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeSolver:
    def __init__(self, results: SolveResult | tuple[SolveResult, ...]) -> None:
        self.results = list(results if isinstance(results, tuple) else (results,))

    def solve(self, _state: BoardState) -> SolveResult:
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def sample_recognition(
    birds: tuple[tuple[int, ...], ...] = ((0,), ()),
) -> RecognitionResult:
    branches = []
    for index, contents in enumerate(birds):
        side = "left" if index % 2 == 0 else "right"
        base = 10 if side == "left" else 90
        direction = 1 if side == "left" else -1
        y = 60 + index * 20
        branches.append(
            DetectedBranch(
                side,
                y + 10,
                y,
                tuple((base + direction * slot * 10, y) for slot in range(4)),
                contents,
            )
        )
    bird_types = sorted({bird for branch in birds for bird in branch})
    type_count = len(bird_types)
    cluster_sizes = tuple(
        sum(branch.count(bird_type) for branch in birds)
        for bird_type in bird_types
    )
    return RecognitionResult(
        BoardState(birds),
        tuple(branches),
        type_count,
        cluster_sizes,
        None,
        (100, 200),
    )


def solve_result(*moves: Move, solved: bool = False) -> SolveResult:
    return SolveResult(tuple(moves), 0, 2, 10, 0.01, solved)


class PlayTests(unittest.TestCase):
    def test_destination_click_uses_slot_farthest_from_source(self) -> None:
        branch = DetectedBranch(
            "right",
            1448,
            1397,
            ((1160, 1397), (1071, 1397), (982, 1397), (893, 1397)),
            (),
        )

        destination = _destination_click_point(branch, (982, 1525))

        self.assertEqual(destination, (1160, 1446))

    def test_physical_state_key_keeps_positions_but_ignores_label_ids(self) -> None:
        first = BoardState(((7, 3), (), (3, 7)))
        relabelled = BoardState(((4, 9), (), (9, 4)))
        moved = BoardState(((7,), (3,), (3, 7)))

        self.assertEqual(_physical_state_key(first), _physical_state_key(relabelled))
        self.assertNotEqual(_physical_state_key(first), _physical_state_key(moved))

    def test_analyze_saves_debug_report_to_default_sibling_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "screenshot.png"
            recognizer = FakeRecognizer(sample_recognition())
            args = build_parser().parse_args(
                ["analyze", str(image_path), "--no-html"]
            )

            with (
                patch("suanniao.cli._recognizer", return_value=recognizer),
                patch(
                    "suanniao.cli._solver",
                    return_value=FakeSolver(solve_result(Move(0, 1, 1))),
                ),
                redirect_stdout(io.StringIO()),
            ):
                exit_code = analyze(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                recognizer.debug_directories,
                [Path(directory) / "screenshot-clusters"],
            )

    def test_each_run_directory_is_unique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _create_run_directory(root)
            second = _create_run_directory(root)

            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertNotEqual(first, second)

    def test_play_saves_screenshot_and_passes_turn_cluster_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory) / "run-test"
            run_directory.mkdir()
            controller = FakeController()
            recognizer = FakeRecognizer(sample_recognition())
            args = build_parser().parse_args(["play", "--dry-run"])

            with (
                patch("suanniao.cli._create_run_directory", return_value=run_directory),
                patch("suanniao.cli._controller", return_value=controller),
                patch("suanniao.cli._recognizer", return_value=recognizer),
                patch(
                    "suanniao.cli._solver",
                    return_value=FakeSolver(solve_result(Move(0, 1, 1))),
                ),
            ):
                exit_code = play(args)

            self.assertEqual(exit_code, 0)
            self.assertTrue((run_directory / "turn-001.png").is_file())
            self.assertEqual(
                recognizer.debug_directories,
                [run_directory / "turn-001-clusters"],
            )
            self.assertEqual(controller.dismiss_calls, 0)
            self.assertEqual(controller.taps, [])
            self.assertTrue(controller.closed)
            self.assertEqual(
                controller.stable_capture_options,
                [{"interval": 0.10, "attempts": 5}],
            )

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_interruption_is_closed_then_manual_prompt_is_shown_if_needed(
        self, _sleep: object
    ) -> None:
        ad_one = solid_image("black")
        ad_two = solid_image("gray")
        board = solid_image("white")
        controller = FakeController(
            stable_screenshots=(ad_one, ad_two, board),
            dismiss_results=(True, False),
        )
        recognizer = FakeRecognizer(
            sample_recognition(),
            board_results=(False, False, True),
        )
        args = build_parser().parse_args(["play"])

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                screenshot, result = _capture_game_board(
                    controller,
                    recognizer,
                    args,
                    Path(directory),
                    "turn-001",
                )

            self.assertIs(screenshot, board)
            self.assertIs(result, recognizer.results[0])
            self.assertEqual(controller.dismiss_calls, 2)
            self.assertIn("已自动点击", output.getvalue())
            self.assertIn("请手动关闭广告窗口", output.getvalue())
            self.assertIn("已重新检测到游戏棋盘", output.getvalue())
            self.assertTrue(
                (Path(directory) / "turn-001-interruption-001.png").is_file()
            )
            self.assertTrue(
                (Path(directory) / "turn-001-interruption-002.png").is_file()
            )

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_branch_elimination_forces_screenshot_and_replanning(
        self, _sleep: object
    ) -> None:
        first_recognition = sample_recognition(
            ((0,), (0, 0, 0), (1,), (1, 1, 1))
        )
        second_recognition = sample_recognition(((1,), (1, 1, 1)))
        first_solution = solve_result(
            Move(0, 1, 1, True),
            Move(2, 3, 1, True),
            solved=True,
        )
        second_solution = solve_result(Move(0, 1, 1, True), solved=True)
        controller = FakeController(
            stable_screenshots=(solid_image("white"), solid_image("white"))
        )
        recognizer = FakeRecognizer(
            (first_recognition, second_recognition),
            board_results=(True, True),
        )
        args = build_parser().parse_args(
            [
                "play",
                "--moves-per-plan",
                "2",
                "--tap-gap",
                "0",
                "--move-wait",
                "0",
                "--elimination-wait",
                "0",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "suanniao.cli._create_run_directory",
                    return_value=Path(directory),
                ),
                patch("suanniao.cli._controller", return_value=controller),
                patch("suanniao.cli._recognizer", return_value=recognizer),
                patch(
                    "suanniao.cli._solver",
                    return_value=FakeSolver((first_solution, second_solution)),
                ),
            ):
                exit_code = play(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(controller.taps), 4)
        self.assertEqual(len(controller.stable_capture_options), 2)
        self.assertEqual(
            recognizer.debug_directories,
            [
                Path(directory) / "turn-001-clusters",
                Path(directory) / "turn-002-clusters",
            ],
        )
        self.assertEqual(controller.dismiss_calls, 0)
        self.assertTrue(controller.closed)

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_mid_batch_interruption_stops_later_taps_and_recovers(
        self, _sleep: object
    ) -> None:
        board = solid_image("white")
        ad = solid_image("black")
        recognition = sample_recognition(
            ((0,), (0, 0), (1,), (1, 1, 1), (0,))
        )
        first_solution = solve_result(
            Move(0, 1, 1),
            Move(4, 1, 1, True),
        )
        controller = FakeController(
            stable_screenshots=(board, ad, board),
            quick_screenshots=(ad,),
            dismiss_results=(True,),
        )
        recognizer = FakeRecognizer(
            (recognition, recognition),
            board_results=(True, False, False, True),
        )
        solver = FakeSolver((first_solution, solve_result()))
        args = build_parser().parse_args(
            [
                "play",
                "--moves-per-plan",
                "2",
                "--tap-gap",
                "0",
                "--move-wait",
                "0",
                "--elimination-wait",
                "0",
            ]
        )

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(output):
            with (
                patch(
                    "suanniao.cli._create_run_directory",
                    return_value=Path(directory),
                ),
                patch("suanniao.cli._controller", return_value=controller),
                patch("suanniao.cli._recognizer", return_value=recognizer),
                patch("suanniao.cli._solver", return_value=solver),
            ):
                exit_code = play(args)
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(controller.taps), 2)
        self.assertEqual(controller.dismiss_calls, 1)
        self.assertIn("批量操作中检测到非棋盘画面", output.getvalue())
        self.assertIn("已自动点击", output.getvalue())

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_failed_move_stops_batch_and_clears_stale_selection(
        self, _sleep: object
    ) -> None:
        board = solid_image("white")
        unchanged = sample_recognition(((0,), (), (1,), ()))
        first_solution = solve_result(
            Move(0, 1, 1),
            Move(2, 3, 1),
        )
        controller = FakeController(
            stable_screenshots=(board, board),
            quick_screenshots=(board,),
        )
        recognizer = FakeRecognizer((unchanged, unchanged, unchanged))
        solver = FakeSolver((first_solution, solve_result()))
        args = build_parser().parse_args(
            [
                "play",
                "--moves-per-plan",
                "2",
                "--tap-gap",
                "0",
                "--move-wait",
                "0",
                "--elimination-wait",
                "0",
            ]
        )

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(output):
            with (
                patch(
                    "suanniao.cli._create_run_directory",
                    return_value=Path(directory),
                ),
                patch("suanniao.cli._controller", return_value=controller),
                patch("suanniao.cli._recognizer", return_value=recognizer),
                patch("suanniao.cli._solver", return_value=solver),
            ):
                exit_code = play(args)

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(controller.taps), 2)
        self.assertGreaterEqual(len(controller.clear_selection_calls), 2)
        self.assertIn("实际棋盘与预期不一致", output.getvalue())

    def test_play_defaults_favor_fast_rolling_batches(self) -> None:
        args = build_parser().parse_args(["play", "--platform", "ios"])

        self.assertEqual(args.moves_per_plan, 8)
        self.assertEqual(args.beam_width, 120)
        self.assertEqual(args.time_limit, 2.0)
        self.assertEqual(args.tap_gap, 0.12)
        self.assertEqual(args.move_wait, 0.30)
        self.assertEqual(args.elimination_wait, 0.55)
        self.assertEqual(args.capture_interval, 0.10)


if __name__ == "__main__":
    unittest.main()
