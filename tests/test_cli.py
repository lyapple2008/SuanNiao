import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from suanniao.cli import (
    _wait_for_board,
    _wait_for_interaction_recovery,
    build_parser,
)
from suanniao.model import BoardState
from suanniao.vision import RecognitionError


class FakeController:
    def __init__(self, screenshots, dismiss_results=()):
        self.screenshots = list(screenshots)
        self.dismiss_results = list(dismiss_results)
        self.dismiss_calls = 0

    def capture_stable(self):
        if len(self.screenshots) > 1:
            return self.screenshots.pop(0)
        return self.screenshots[0]

    def dismiss_ad(self):
        self.dismiss_calls += 1
        if self.dismiss_results:
            return self.dismiss_results.pop(0)
        return False


class FakeRecognizer:
    def __init__(self, results):
        self.results = list(results)

    def read(self, _screenshot):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def recognition(branches=((0,),)):
    return SimpleNamespace(state=BoardState(tuple(branches)))


class AdRecoveryTests(unittest.TestCase):
    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_unrecognizable_ad_is_closed_then_board_resumes(self, _sleep) -> None:
        ad = Image.new("RGB", (100, 200), "black")
        board = Image.new("RGB", (100, 200), "white")
        expected = recognition()
        controller = FakeController([ad, board], dismiss_results=[True])
        recognizer = FakeRecognizer([RecognitionError("no board"), expected])

        screenshot, result = _wait_for_board(
            controller,
            recognizer,
            ad_mode="auto",
            timeout=10,
            poll_interval=0.01,
            allow_dismiss=True,
        )

        self.assertIs(screenshot, board)
        self.assertIs(result, expected)
        self.assertEqual(controller.dismiss_calls, 1)

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_dry_run_waits_without_tapping_ad(self, _sleep) -> None:
        ad = Image.new("RGB", (100, 200), "black")
        board = Image.new("RGB", (100, 200), "white")
        expected = recognition()
        controller = FakeController([ad, board], dismiss_results=[True])
        recognizer = FakeRecognizer([RecognitionError("no board"), expected])

        _wait_for_board(
            controller,
            recognizer,
            ad_mode="auto",
            timeout=10,
            poll_interval=0.01,
            allow_dismiss=False,
        )

        self.assertEqual(controller.dismiss_calls, 0)

    @patch("suanniao.cli.time.sleep", return_value=None)
    def test_partial_ad_waits_for_changed_stable_board(self, _sleep) -> None:
        blocked = Image.new("RGB", (100, 200), "black")
        restored_one = Image.new("RGB", (100, 200), "white")
        restored_two = Image.new("RGB", (100, 200), "white")
        expected = recognition(((0,), ()))
        controller = FakeController([restored_one, restored_two])
        recognizer = FakeRecognizer([expected, expected])

        screenshot, result = _wait_for_interaction_recovery(
            controller,
            recognizer,
            blocked,
            ad_mode="wait",
            timeout=10,
            poll_interval=0.01,
            allow_dismiss=True,
        )

        self.assertIs(screenshot, restored_two)
        self.assertIs(result, expected)
        self.assertEqual(controller.dismiss_calls, 0)

    def test_ad_options_have_safe_defaults(self) -> None:
        args = build_parser().parse_args(["play", "--platform", "ios"])

        self.assertEqual(args.ad_mode, "wait")
        self.assertEqual(args.ad_wait_timeout, 300.0)
        self.assertEqual(args.ad_poll_interval, 1.0)
        self.assertEqual(args.interaction_retries, 2)


if __name__ == "__main__":
    unittest.main()
