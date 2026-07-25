from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .model import BoardState, Move, REMOVED


@dataclass(frozen=True, slots=True)
class SolveResult:
    moves: tuple[Move, ...]
    eliminated: int
    target: int
    explored_states: int
    elapsed_seconds: float
    solved: bool


class BeamSolver:
    """A bounded global search that favors merges and completed branches."""

    def __init__(
        self,
        *,
        beam_width: int = 2_000,
        max_depth: int = 80,
        time_limit: float | None = 20.0,
    ) -> None:
        if beam_width < 1:
            raise ValueError("beam_width must be positive")
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.time_limit = time_limit

    def solve(self, initial: BoardState) -> SolveResult:
        started = monotonic()
        target = initial.target_removed_count
        if initial.is_finished:
            return SolveResult((), initial.removed_count, target, 1, 0.0, True)

        # Each beam item keeps a valid labeled state and its executable path.
        beam: list[tuple[BoardState, tuple[Move, ...]]] = [(initial, ())]
        seen = {initial.canonical_key()}
        best_state = initial
        best_path: tuple[Move, ...] = ()
        best_rank = self._rank(initial)

        for _depth in range(1, self.max_depth + 1):
            if self.time_limit is not None and monotonic() - started >= self.time_limit:
                break

            candidates: list[
                tuple[tuple[int, ...], BoardState, tuple[Move, ...]]
            ] = []

            for state, path in beam:
                for move in state.legal_moves():
                    next_state = state.apply(move)
                    key = next_state.canonical_key()
                    if key in seen:
                        continue
                    seen.add(key)

                    next_path = path + (move,)
                    rank = self._rank(next_state)
                    if rank > best_rank:
                        best_state = next_state
                        best_path = next_path
                        best_rank = rank

                    if next_state.removed_count >= target:
                        elapsed = monotonic() - started
                        return SolveResult(
                            next_path,
                            next_state.removed_count,
                            target,
                            len(seen),
                            elapsed,
                            True,
                        )

                    candidates.append((rank, next_state, next_path))

            if not candidates:
                break

            candidates.sort(key=lambda item: item[0], reverse=True)
            beam = [
                (state, path)
                for _rank, state, path in candidates[: self.beam_width]
            ]

        elapsed = monotonic() - started
        return SolveResult(
            best_path,
            best_state.removed_count,
            target,
            len(seen),
            elapsed,
            best_state.removed_count >= target,
        )

    @staticmethod
    def _rank(state: BoardState) -> tuple[int, ...]:
        runs = 0
        uniform_weight = 0
        locked_mixed = 0
        empty_count = 0

        for branch in state.branches:
            if branch == REMOVED:
                continue
            if not branch:
                empty_count += 1
                continue

            branch_runs = 1 + sum(
                left != right for left, right in zip(branch, branch[1:])
            )
            runs += branch_runs
            if branch_runs == 1:
                uniform_weight += len(branch) ** 2
            elif len(branch) == state.capacity:
                locked_mixed += 1

        # Lexicographic ordering guarantees that eliminating one more branch
        # is always better than any cosmetic improvement to the board.
        return (
            state.removed_count,
            -runs,
            uniform_weight,
            -locked_mixed,
            empty_count,
        )

