import unittest

from suanniao.model import BoardState, REMOVED
from suanniao.solver import BeamSolver


REFERENCE_BRANCHES = (
    (0, 1, 2, 2),
    (3, 4),
    (6, 0, 5, 1),
    (6, 3, 2, 6),
    (4, 1, 3, 2),
    (5, 1, 2, 2),
    (2, 0, 4, 6),
    (3, 3, 3),
    (2, 1),
    (1, 0, 1, 4),
    (6, 1, 5, 4),
    (4, 1, 5, 1),
    (5, 6, 3, 1),
    (4, 0, 6, 4),
    (5, 2, 2, 1),
    (3, 5, 2),
    (0, 5),
    (0, 6, 0, 2),
)


class SolverTests(unittest.TestCase):
    def test_reference_board_is_fully_solved(self) -> None:
        initial = BoardState(REFERENCE_BRANCHES)
        result = BeamSolver(beam_width=1_000, time_limit=20).solve(initial)

        self.assertTrue(result.solved)
        self.assertEqual(result.eliminated, 16)
        self.assertGreater(len(result.moves), 0)

        state = initial
        for move in result.moves:
            state = state.apply(move)
        self.assertEqual(state.bird_count, 0)
        self.assertEqual(sum(branch == REMOVED for branch in state.branches), 16)

    def test_a_completed_destination_disappears(self) -> None:
        state = BoardState(((0, 0), (0, 0), ()))
        move = next(
            move
            for move in state.legal_moves()
            if move.source == 0 and move.destination == 1
        )
        result = state.apply(move)
        self.assertEqual(result.branches[1], REMOVED)
        self.assertEqual(result.branches[0], ())


if __name__ == "__main__":
    unittest.main()

