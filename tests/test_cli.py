import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from suanniao.cli import _create_run_directory, build_parser, play
from suanniao.model import BoardState, Move
from suanniao.solver import SolveResult
from suanniao.vision import DetectedBranch, RecognitionResult


class FakeController:
    def __init__(self) -> None:
        self.closed = False

    def capture_stable(self) -> Image.Image:
        return Image.new("RGB", (100, 200), (120, 180, 220))

    def tap(self, _x: int, _y: int) -> None:
        raise AssertionError("dry-run must not tap")

    def close(self) -> None:
        self.closed = True


class FakeRecognizer:
    def __init__(self, result: RecognitionResult) -> None:
        self.result = result
        self.debug_directories: list[Path] = []

    def read(self, _screenshot: Image.Image, *, debug_dir: Path) -> RecognitionResult:
        self.debug_directories.append(debug_dir)
        return self.result


class FakeSolver:
    def solve(self, _state: BoardState) -> SolveResult:
        return SolveResult((Move(0, 1, 1),), 0, 1, 1, 0.0, False)


def sample_recognition() -> RecognitionResult:
    branches = (
        DetectedBranch(
            "left",
            100,
            90,
            ((10, 90), (20, 90), (30, 90), (40, 90)),
            (0,),
        ),
        DetectedBranch(
            "right",
            100,
            90,
            ((90, 90), (80, 90), (70, 90), (60, 90)),
            (),
        ),
    )
    return RecognitionResult(
        BoardState(tuple(branch.birds for branch in branches)),
        branches,
        1,
        (1,),
        None,
        (100, 200),
    )


class PlayDebugOutputTests(unittest.TestCase):
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
                patch("suanniao.cli._solver", return_value=FakeSolver()),
            ):
                exit_code = play(args)

            self.assertEqual(exit_code, 0)
            self.assertTrue((run_directory / "turn-001.png").is_file())
            self.assertEqual(
                recognizer.debug_directories,
                [run_directory / "turn-001-clusters"],
            )
            self.assertTrue(controller.closed)


if __name__ == "__main__":
    unittest.main()
