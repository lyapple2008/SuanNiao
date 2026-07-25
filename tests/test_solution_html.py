import tempfile
import unittest
from pathlib import Path

from suanniao.model import BoardState, Move
from suanniao.solution_html import write_solution_animation
from suanniao.solver import SolveResult
from suanniao.vision import DetectedBranch, RecognitionResult


class SolutionHtmlTests(unittest.TestCase):
    def test_writes_board_layout_and_moves(self) -> None:
        branches = (
            DetectedBranch(
                "left",
                220,
                208,
                ((25, 208), (75, 208), (125, 208), (175, 208)),
                (0, 0),
            ),
            DetectedBranch(
                "right",
                320,
                308,
                ((295, 308), (245, 308), (195, 308), (145, 308)),
                (0, 0),
            ),
            DetectedBranch(
                "left",
                420,
                408,
                ((25, 408), (75, 408), (125, 408), (175, 408)),
                (),
            ),
        )
        recognition = RecognitionResult(
            BoardState(((0, 0), (0, 0), ()), 4),
            branches,
            1,
            (4,),
            None,
            (320, 640),
        )
        solution = SolveResult(
            (Move(0, 1, 2, True),),
            eliminated=1,
            target=1,
            explored_states=2,
            elapsed_seconds=0.01,
            solved=True,
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "solution.html"
            write_solution_animation(
                recognition, solution, output, source_name="board.png"
            )
            document = output.read_text(encoding="utf-8")

        self.assertIn("board.png · 算鸟消除动画", document)
        self.assertIn('"width":320', document)
        self.assertIn('"slots":[[25,208],[75,208]', document)
        self.assertIn('"source":0,"destination":1,"count":2', document)
        self.assertIn('"completesBranch":true', document)
        self.assertIn('const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"', document)
        self.assertIn('playButton.addEventListener("click", play)', document)
        self.assertNotIn("setTimeout(play, 500)", document)


if __name__ == "__main__":
    unittest.main()
