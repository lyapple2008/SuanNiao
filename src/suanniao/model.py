from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

Bird: TypeAlias = int
Branch: TypeAlias = tuple[Bird, ...]

# A completed branch disappears and is no longer a usable destination.
REMOVED: Branch = (-1,)


@dataclass(frozen=True, slots=True)
class Move:
    source: int
    destination: int
    count: int
    completes_branch: bool = False


@dataclass(frozen=True, slots=True)
class BoardState:
    """Branches are stored from their fixed/base end toward the movable end."""

    branches: tuple[Branch, ...]
    capacity: int = 4

    @property
    def bird_count(self) -> int:
        return sum(len(branch) for branch in self.branches if branch != REMOVED)

    @property
    def removed_count(self) -> int:
        return sum(branch == REMOVED for branch in self.branches)

    @property
    def target_removed_count(self) -> int:
        return self.removed_count + self.bird_count // self.capacity

    @property
    def is_finished(self) -> bool:
        return self.bird_count == 0

    def canonical_key(self) -> tuple[Branch, ...]:
        # Branch locations do not affect the puzzle rules, so symmetric states
        # can share one search entry. REMOVED=(-1,) sorts before normal birds.
        return tuple(sorted(self.branches))

    def legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        first_empty = next(
            (index for index, branch in enumerate(self.branches) if branch == ()),
            -1,
        )

        for source, source_branch in enumerate(self.branches):
            if not source_branch or source_branch == REMOVED:
                continue

            bird = source_branch[-1]
            run = 1
            while run < len(source_branch) and source_branch[-1 - run] == bird:
                run += 1

            source_is_uniform = run == len(source_branch)

            for destination, destination_branch in enumerate(self.branches):
                if source == destination or destination_branch == REMOVED:
                    continue
                if len(destination_branch) >= self.capacity:
                    continue

                if destination_branch:
                    if destination_branch[-1] != bird:
                        continue
                else:
                    # Empty branches are interchangeable. Moving a uniform
                    # branch to an empty one only renames two branches.
                    if source_is_uniform or destination != first_empty:
                        continue

                count = min(run, self.capacity - len(destination_branch))
                merged = destination_branch + (bird,) * count
                completes = (
                    len(merged) == self.capacity
                    and all(item == bird for item in merged)
                )
                moves.append(Move(source, destination, count, completes))

        return moves

    def apply(self, move: Move) -> "BoardState":
        source = self.branches[move.source]
        destination = self.branches[move.destination]
        if not source or source == REMOVED or destination == REMOVED:
            raise ValueError(f"Illegal move: {move}")

        bird = source[-1]
        run = 1
        while run < len(source) and source[-1 - run] == bird:
            run += 1

        if destination and destination[-1] != bird:
            raise ValueError(f"Destination does not have the same outer bird: {move}")
        if move.count != min(run, self.capacity - len(destination)):
            raise ValueError(f"Move count does not match game behavior: {move}")

        branches = list(self.branches)
        branches[move.source] = source[: -move.count]
        merged = destination + (bird,) * move.count
        branches[move.destination] = (
            REMOVED
            if len(merged) == self.capacity and len(set(merged)) == 1
            else merged
        )
        return BoardState(tuple(branches), self.capacity)

