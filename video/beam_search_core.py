from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    AnimationGroup,
    ArcBetweenPoints,
    Arrow,
    Circle,
    Create,
    Cross,
    DashedLine,
    DOWN,
    DR,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    LaggedStart,
    LEFT,
    Line,
    ManimColor,
    MoveAlongPath,
    ORIGIN,
    PI,
    Rectangle,
    ReplacementTransform,
    RIGHT,
    RoundedRectangle,
    Scene,
    Star,
    Text,
    UP,
    UR,
    VGroup,
    WHITE,
    config,
)
from manim.utils.rate_functions import ease_in_out_cubic, ease_out_back, ease_out_cubic


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suanniao.model import BoardState, Move, REMOVED  # noqa: E402


TARGET_DURATION = 90.0
FONT = "Hiragino Sans GB"

SKY = ManimColor("#BDEBFA")
SKY_DEEP = ManimColor("#8FD5F0")
CLOUD = ManimColor("#F8FDFF")
INK = ManimColor("#23364A")
MUTED = ManimColor("#6B7E8F")
WOOD = ManimColor("#8D552F")
KEEP = ManimColor("#2FA36B")
KEEP_LIGHT = ManimColor("#BFEED6")
DANGER = ManimColor("#E05B52")
GOLD = ManimColor("#F4B942")
CARD = ManimColor("#F9FDFF")
CARD_BORDER = ManimColor("#D2E7EE")

BIRD_COLORS = (
    ManimColor("#4E79A7"),  # blue
    ManimColor("#F2BE42"),  # gold
    ManimColor("#E76F51"),  # coral
    ManimColor("#7A5195"),  # purple
)
BIRD_LETTERS = ("A", "B", "C", "D")


INITIAL_STATE = BoardState(
    (
        (0, 3, 3, 2),
        (1, 2, 1, 2),
        (3, 1, 0, 0),
        (3, 1, 0, 2),
        (),
        (),
    ),
    capacity=4,
)

GREEDY_MOVES = (
    Move(2, 4, 2, False),
    Move(2, 5, 1, False),
)

SOLUTION_MOVES = (
    Move(0, 4, 1, False),
    Move(3, 4, 1, False),
    Move(0, 5, 2, False),
    Move(2, 0, 2, False),
    Move(3, 0, 1, True),
    Move(1, 4, 1, False),
    Move(1, 2, 1, False),
    Move(1, 4, 1, True),
    Move(2, 1, 2, False),
    Move(3, 1, 1, True),
    Move(2, 5, 1, False),
    Move(3, 5, 1, True),
)


def validate_story_data() -> None:
    greedy_state = INITIAL_STATE
    for move in GREEDY_MOVES:
        greedy_state = greedy_state.apply(move)
    if greedy_state.legal_moves():
        raise RuntimeError("The width-1 teaching route must be stuck after two moves")

    solution_state = INITIAL_STATE
    for move in SOLUTION_MOVES:
        solution_state = solution_state.apply(move)
    if not solution_state.is_finished:
        raise RuntimeError("The twelve-move teaching route must solve the board")


validate_story_data()


def label(text: str, size: int = 42, color=INK, weight="SEMIBOLD") -> Text:
    return Text(text, font=FONT, font_size=size, color=color, weight=weight)


def branch_positions() -> tuple[np.ndarray, ...]:
    return (
        np.array([-3.65, 1.85, 0.0]),
        np.array([3.65, 1.85, 0.0]),
        np.array([-3.65, 0.0, 0.0]),
        np.array([3.65, 0.0, 0.0]),
        np.array([-3.65, -1.85, 0.0]),
        np.array([3.65, -1.85, 0.0]),
    )


def make_background() -> VGroup:
    backdrop = Rectangle(
        width=config.frame_width,
        height=config.frame_height,
        stroke_width=0,
        fill_color=SKY,
        fill_opacity=1,
    )

    clouds = VGroup()
    cloud_specs = (
        (-5.5, 2.6, 0.72),
        (5.65, 2.0, 0.58),
        (-5.8, -2.8, 0.52),
        (5.0, -2.55, 0.78),
    )
    for x, y, scale in cloud_specs:
        puff = VGroup(
            Circle(radius=0.48),
            Circle(radius=0.62).shift(RIGHT * 0.48 + UP * 0.12),
            Circle(radius=0.42).shift(RIGHT * 1.0),
            RoundedRectangle(width=1.7, height=0.58, corner_radius=0.28).shift(
                RIGHT * 0.5 + DOWN * 0.23
            ),
        )
        puff.set_fill(CLOUD, opacity=0.38).set_stroke(width=0)
        puff.scale(scale).move_to(np.array([x, y, 0.0]))
        clouds.add(puff)

    haze = Rectangle(
        width=config.frame_width,
        height=1.4,
        stroke_width=0,
        fill_color=WHITE,
        fill_opacity=0.12,
    ).to_edge(DOWN, buff=0)
    return VGroup(backdrop, clouds, haze)


class BirdIcon(VGroup):
    """A colored circular token with a letter identifying the bird type."""

    def __init__(self, bird_type: int, scale_factor: float = 1.0):
        super().__init__()
        color = BIRD_COLORS[bird_type]
        text_color = INK if bird_type == 1 else WHITE

        body = Circle(
            radius=0.34,
            fill_color=color,
            fill_opacity=1,
            stroke_color=INK,
            stroke_width=2.4,
        )
        letter = Text(
            BIRD_LETTERS[bird_type],
            font=FONT,
            font_size=30,
            color=text_color,
            weight="BOLD",
        ).move_to(body)

        self.add(body, letter)
        self.scale(scale_factor)


def make_branch(center: np.ndarray, side: str) -> VGroup:
    start = center + LEFT * 1.58
    end = center + RIGHT * 1.58
    horizontal = Line(start, end, color=WOOD, stroke_width=8)
    fixed_point = start if side == "left" else end
    fixed_cap = Line(
        fixed_point + DOWN * 0.12,
        fixed_point + UP * 0.78,
        color=WOOD,
        stroke_width=8,
    )
    return VGroup(horizontal, fixed_cap)


def make_stack_example(
    center: np.ndarray,
    side: str,
    bird_types: tuple[int, ...],
) -> tuple[VGroup, VGroup, VGroup, list[np.ndarray]]:
    """Build a single horizontal stack for the opening modeling explanation."""
    branch = make_branch(center, side)
    fixed_slot = center + (LEFT if side == "left" else RIGHT) * 1.22
    toward_center = RIGHT if side == "left" else LEFT
    slots = [fixed_slot + toward_center * 0.81 * slot + UP * 0.36 for slot in range(4)]
    birds = VGroup(
        *[
            BirdIcon(bird_type, scale_factor=0.92).move_to(slots[index])
            for index, bird_type in enumerate(bird_types)
        ]
    )
    branch.set_z_index(0)
    birds.set_z_index(2)
    return VGroup(branch, birds), branch, birds, slots


class BirdBoard:
    def __init__(self, state: BoardState):
        self.state = state
        self.positions = branch_positions()
        self.slot_points: list[list[np.ndarray]] = []
        self.branch_groups: list[VGroup] = []
        self.birds: list[list[BirdIcon]] = []
        self.group = VGroup()

        for index, (center, branch) in enumerate(zip(self.positions, state.branches)):
            side = "left" if index % 2 == 0 else "right"
            branch_group = make_branch(center, side)
            fixed_slot = center + (LEFT if side == "left" else RIGHT) * 1.22
            toward_center = RIGHT if side == "left" else LEFT
            slots = [fixed_slot + toward_center * 0.81 * slot + UP * 0.36 for slot in range(4)]
            bird_mobjects: list[BirdIcon] = []

            if branch == REMOVED:
                branch_group.set_opacity(0)
            else:
                for bird_type, point in zip(branch, slots):
                    bird = BirdIcon(bird_type, scale_factor=0.92).move_to(point)
                    bird_mobjects.append(bird)
                    self.group.add(bird)

            self.slot_points.append(slots)
            self.branch_groups.append(branch_group)
            self.birds.append(bird_mobjects)
            self.group.add(branch_group)

        # Put branches behind birds even though they were added later.
        for branch_group in self.branch_groups:
            branch_group.set_z_index(0)
        for branch_birds in self.birds:
            for bird in branch_birds:
                bird.set_z_index(2)

    def move_animation(
        self,
        scene: "BeamSearchCore",
        move: Move,
        move_time: float = 1.0,
        completion_time: float = 0.55,
    ) -> None:
        moving = self.birds[move.source][-move.count :]
        destination_start = len(self.birds[move.destination])

        source_glow = self.branch_groups[move.source].copy().set_color(GOLD).set_opacity(0.58)
        destination_glow = (
            self.branch_groups[move.destination].copy().set_color(KEEP).set_opacity(0.58)
        )
        source_glow.set_z_index(1)
        destination_glow.set_z_index(1)
        scene.add(source_glow, destination_glow)

        flights = []
        for offset, bird in enumerate(moving):
            target = self.slot_points[move.destination][destination_start + offset]
            delta_y = target[1] - bird.get_center()[1]
            angle = -PI / 3 if delta_y >= 0 else PI / 3
            if abs(delta_y) < 0.15:
                angle = -PI / 4
            path = ArcBetweenPoints(bird.get_center(), target, angle=angle)
            flights.append(MoveAlongPath(bird, path, rate_func=ease_in_out_cubic))

        scene.tplay(
            AnimationGroup(*flights, lag_ratio=0.08),
            source_glow.animate.set_opacity(0),
            destination_glow.animate.set_opacity(0),
            run_time=move_time,
        )
        scene.remove(source_glow, destination_glow)

        self.birds[move.source] = self.birds[move.source][: -move.count]
        self.birds[move.destination].extend(moving)
        self.state = self.state.apply(move)

        if move.completes_branch:
            center = self.positions[move.destination] + UP * 0.2
            bursts = VGroup(
                *[
                    Star(
                        n=5,
                        outer_radius=0.12,
                        inner_radius=0.055,
                        fill_color=GOLD,
                        fill_opacity=1,
                        stroke_width=0,
                    ).move_to(center + direction)
                    for direction in (
                        UP * 0.65,
                        UR * 0.55,
                        RIGHT * 0.75,
                        DR * 0.55,
                        LEFT * 0.75,
                    )
                ]
            )
            completed = VGroup(self.branch_groups[move.destination], *self.birds[move.destination])
            scene.tplay(
                LaggedStart(*[GrowFromCenter(star) for star in bursts], lag_ratio=0.08),
                completed.animate.scale(1.06).set_opacity(0),
                run_time=completion_time,
                rate_func=ease_out_cubic,
            )
            scene.remove(completed, bursts)

    def reverse_animation(
        self,
        scene: "BeamSearchCore",
        move: Move,
        previous_state: BoardState,
        run_time: float,
    ) -> None:
        moving = self.birds[move.destination][-move.count :]
        source_start = len(self.birds[move.source])
        flights = []
        for offset, bird in enumerate(moving):
            target = self.slot_points[move.source][source_start + offset]
            path = ArcBetweenPoints(bird.get_center(), target, angle=PI / 3)
            flights.append(MoveAlongPath(bird, path, rate_func=ease_in_out_cubic))
        scene.tplay(AnimationGroup(*flights, lag_ratio=0.08), run_time=run_time)
        self.birds[move.destination] = self.birds[move.destination][: -move.count]
        self.birds[move.source].extend(moving)
        self.state = previous_state


class SnapshotCard(VGroup):
    def __init__(self, state: BoardState, width: float = 2.65, height: float = 2.15):
        super().__init__()
        self.frame = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.18,
            fill_color=CARD,
            fill_opacity=0.97,
            stroke_color=CARD_BORDER,
            stroke_width=2.2,
        )
        self.add(self.frame)

        x_centers = (-0.62, 0.62)
        y_centers = (0.62, 0.0, -0.62)
        branch_index = 0
        for y in y_centers:
            for x in x_centers:
                branch = state.branches[branch_index]
                side = "left" if branch_index % 2 == 0 else "right"
                start = np.array([x - 0.49, y - 0.11, 0.0])
                end = np.array([x + 0.49, y - 0.11, 0.0])
                line = Line(
                    start,
                    end,
                    color=WOOD,
                    stroke_width=3.3,
                )
                if branch == REMOVED:
                    line = DashedLine(
                        start,
                        end,
                        color=KEEP,
                        stroke_width=2.2,
                        dash_length=0.08,
                    ).set_opacity(0.42)
                self.add(line)

                if branch != REMOVED:
                    fixed_point = start if side == "left" else end
                    fixed_cap = Line(
                        fixed_point + DOWN * 0.03,
                        fixed_point + UP * 0.28,
                        color=WOOD,
                        stroke_width=3.3,
                    )
                    self.add(fixed_cap)
                    fixed_x = x - 0.36 if side == "left" else x + 0.36
                    direction = 1 if side == "left" else -1
                    for slot, bird_type in enumerate(branch):
                        point = np.array(
                            [fixed_x + direction * slot * 0.24, y + 0.02, 0.0]
                        )
                        body = Circle(
                            radius=0.105,
                            fill_color=BIRD_COLORS[bird_type],
                            fill_opacity=1,
                            stroke_color=INK,
                            stroke_width=0.7,
                        ).move_to(point)
                        text_color = INK if bird_type == 1 else WHITE
                        letter = Text(
                            BIRD_LETTERS[bird_type],
                            font=FONT,
                            font_size=8,
                            color=text_color,
                            weight="BOLD",
                        ).move_to(point)
                        self.add(body, letter)
                branch_index += 1


def rank_state(state: BoardState) -> tuple[int, ...]:
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
        branch_runs = 1 + sum(left != right for left, right in zip(branch, branch[1:]))
        runs += branch_runs
        if branch_runs == 1:
            uniform_weight += len(branch) ** 2
        elif len(branch) == state.capacity:
            locked_mixed += 1
    return state.removed_count, -runs, uniform_weight, -locked_mixed, empty_count


def next_beam(states: list[BoardState], width: int = 3) -> tuple[list[BoardState], list[BoardState]]:
    seen: set[tuple[tuple[int, ...], ...]] = set()
    candidates: list[BoardState] = []
    for state in states:
        for move in state.legal_moves():
            child = state.apply(move)
            key = child.canonical_key()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(child)
    candidates.sort(key=rank_state, reverse=True)
    return candidates, candidates[:width]


def make_badge(text: str, color=INK) -> VGroup:
    words = label(text, size=30, color=color)
    frame = RoundedRectangle(
        width=words.width + 0.62,
        height=words.height + 0.34,
        corner_radius=0.2,
        fill_color=WHITE,
        fill_opacity=0.86,
        stroke_color=color,
        stroke_width=2,
    )
    return VGroup(frame, words)


def tree_node(center: np.ndarray, color, radius: float = 0.16) -> VGroup:
    dot = Circle(
        radius=radius,
        fill_color=color,
        fill_opacity=1,
        stroke_color=INK,
        stroke_width=2,
    ).move_to(center)
    return VGroup(dot)


def tree_edge(start: np.ndarray, end: np.ndarray, color=MUTED, width: float = 2.4) -> Line:
    return Line(start, end, color=color, stroke_width=width)


SEARCH_TREE_NODES: dict[str, dict] = {
    "R": {"pos": (0.0, 1.75), "children": ("A", "B", "C")},
    "A": {"pos": (-2.85, 0.35), "children": ("D", "E", "F")},
    "B": {"pos": (0.0, 0.35), "children": ("S_opt",)},
    "C": {"pos": (2.85, 0.35), "children": ("G",)},
    "D": {"pos": (-3.75, -0.75), "children": ("X",)},
    "E": {"pos": (-2.55, -0.75), "children": ()},
    "F": {"pos": (-1.55, -0.75), "children": ("S2",)},
    "G": {"pos": (2.85, -0.75), "children": ("H",)},
    "X": {"pos": (-3.75, -1.85), "children": (), "leaf": "dead"},
    "S2": {"pos": (-1.55, -1.85), "children": (), "leaf": "solution"},
    "S_opt": {"pos": (0.0, -0.75), "children": (), "leaf": "solution", "optimal": True},
    "H": {"pos": (2.85, -1.85), "children": ("S3",)},
    "S3": {"pos": (2.85, -2.75), "children": (), "leaf": "solution"},
}


class SearchTreeGraph:
    """Irregular multi-way search tree for DFS / BFS teaching."""

    def __init__(
        self,
        nodes: dict[str, dict] = SEARCH_TREE_NODES,
        *,
        scale: float = 1.0,
        shift: np.ndarray | None = None,
    ):
        self.nodes = nodes
        self.scale = scale
        self.shift = np.array(shift if shift is not None else (0.0, 0.0, 0.0))
        self.parents: dict[str, str | None] = {"R": None}
        for node_id, data in nodes.items():
            for child in data.get("children", ()):
                self.parents[child] = node_id

        self.node_mobs: dict[str, VGroup] = {}
        self.edge_mobs: dict[tuple[str, str], Line] = {}
        self.path_mobs: dict[tuple[str, str], Line] = {}
        self.cursor = Circle(radius=0.22, stroke_color=GOLD, stroke_width=4, fill_opacity=0)
        self.group = VGroup()

    def _node_center(self, node_id: str) -> np.ndarray:
        x, y = self.nodes[node_id]["pos"]
        return np.array([x * self.scale + self.shift[0], y * self.scale + self.shift[1], 0.0])

    def _node_color(self, node_id: str) -> ManimColor:
        data = self.nodes[node_id]
        if data.get("leaf") == "dead":
            return DANGER
        if data.get("leaf") == "solution":
            return KEEP if data.get("optimal") else GOLD
        return INK

    def _node_radius(self, node_id: str) -> float:
        data = self.nodes[node_id]
        base = 0.13 if data.get("leaf") else 0.15
        return base * self.scale

    def build(self, *, dim_unvisited: bool = True) -> VGroup:
        edges = VGroup()
        for node_id, data in self.nodes.items():
            for child in data.get("children", ()):
                edge = tree_edge(
                    self._node_center(node_id),
                    self._node_center(child),
                    MUTED,
                    max(1.6, 2.2 * self.scale),
                )
                if dim_unvisited:
                    edge.set_opacity(0.38)
                self.edge_mobs[(node_id, child)] = edge
                edges.add(edge)

        nodes = VGroup()
        for node_id in self.nodes:
            center = self._node_center(node_id)
            body = tree_node(center, self._node_color(node_id), self._node_radius(node_id))
            if dim_unvisited:
                body.set_opacity(0.32)
            adornment = self._leaf_adornment(node_id)
            mob = VGroup(body, adornment) if adornment else body
            if adornment and dim_unvisited:
                adornment.set_opacity(0.32)
            self.node_mobs[node_id] = mob
            nodes.add(mob)

        self.group = VGroup(edges, nodes)
        return self.group

    def _leaf_adornment(self, node_id: str):
        data = self.nodes[node_id]
        center = self._node_center(node_id)
        font_size = max(10, int(16 * self.scale))
        if data.get("leaf") == "dead":
            cross = Cross(stroke_color=WHITE, stroke_width=2.4).scale(0.17 * self.scale).move_to(center)
            return cross
        if data.get("leaf") == "solution":
            mark = label("✓", size=font_size, color=WHITE).move_to(center)
            return mark
        return None

    def path_to(self, node_id: str) -> list[str]:
        path: list[str] = []
        current: str | None = node_id
        while current is not None:
            path.append(current)
            current = self.parents.get(current)
        path.reverse()
        return path

    @staticmethod
    def dfs_order(nodes: dict[str, dict], root: str = "R") -> list[str]:
        order: list[str] = []
        stack = [root]
        while stack:
            node = stack.pop()
            order.append(node)
            for child in reversed(nodes[node].get("children", ())):
                stack.append(child)
        return order

    @staticmethod
    def bfs_order(nodes: dict[str, dict], root: str = "R") -> list[str]:
        order: list[str] = []
        queue = [root]
        while queue:
            node = queue.pop(0)
            order.append(node)
            for child in nodes[node].get("children", ()):
                queue.append(child)
        return order

    def first_solution(self, order: list[str]) -> str | None:
        for node_id in order:
            if self.nodes[node_id].get("leaf") == "solution":
                return node_id
        return None

    def reset_highlights(self) -> None:
        for edge in self.edge_mobs.values():
            edge.set_color(MUTED).set_stroke(width=2.2, opacity=1)
        for node_id, mob in self.node_mobs.items():
            body = mob[0]
            body.set_fill(self._node_color(node_id), opacity=1)
            body.set_stroke(INK, width=2)
        for path_line in self.path_mobs.values():
            path_line.set_stroke(opacity=0)
        self.cursor.set_opacity(0)

    def make_path_overlay(self, path: list[str], color, width: float = 5.5) -> VGroup:
        lines = VGroup()
        for start, end in zip(path, path[1:]):
            key = (start, end)
            if key not in self.path_mobs:
                line = tree_edge(
                    self._node_center(start),
                    self._node_center(end),
                    color,
                    width,
                ).set_stroke(opacity=0)
                self.path_mobs[key] = line
                lines.add(line)
            else:
                lines.add(self.path_mobs[key])
        return lines


def make_pruning_demo() -> VGroup:
    """Two branch permutations that share one canonical search key."""
    left_state = BoardState(
        ((0, 1), (2,), (), (), (), ()),
        capacity=4,
    )
    right_state = BoardState(
        ((2,), (0, 1), (), (), (), ()),
        capacity=4,
    )
    left_card = SnapshotCard(left_state, width=2.35, height=1.95).scale(0.82)
    right_card = SnapshotCard(right_state, width=2.35, height=1.95).scale(0.82)
    left_card.move_to(LEFT * 2.55)
    right_card.move_to(RIGHT * 2.55)
    equals = label("=", size=54, color=GOLD).move_to(ORIGIN + UP * 0.05)
    key_text = label("canonical_key() 相同", size=30, color=GOLD).next_to(equals, DOWN, buff=0.55)
    skip = make_badge("seen 集合跳过", DANGER).next_to(key_text, DOWN, buff=0.42)
    caption = label("对称排列 → 同一搜索状态，只保留一条分支", size=28, color=MUTED, weight="NORMAL")
    caption.next_to(skip, DOWN, buff=0.38)
    return VGroup(left_card, right_card, equals, key_text, skip, caption)


def comparison_card(title: str, subtitle: str, color, rays: int, success: bool) -> VGroup:
    card = RoundedRectangle(
        width=3.55,
        height=3.55,
        corner_radius=0.28,
        fill_color=CARD,
        fill_opacity=0.95,
        stroke_color=color,
        stroke_width=3,
    )
    heading = label(title, size=36, color=color).move_to(card.get_top() + DOWN * 0.55)
    sub = label(subtitle, size=24, color=MUTED, weight="NORMAL").move_to(
        card.get_bottom() + UP * 0.42
    )
    origin = card.get_center() + UP * 0.55
    paths = VGroup()
    if rays == 1:
        endpoints = [origin + DOWN * 1.05]
    else:
        endpoints = [
            origin + DOWN * 1.05 + RIGHT * offset
            for offset in np.linspace(-1.05, 1.05, rays)
        ]
    for end in endpoints:
        paths.add(Line(origin, end, color=color, stroke_width=4 if rays < 6 else 2.2))
    start_dot = Circle(radius=0.10, fill_color=color, fill_opacity=1, stroke_width=0).move_to(origin)
    symbol = (
        label("✓", size=48, color=KEEP)
        if success
        else label("×", size=52, color=DANGER)
    ).move_to(card.get_center() + DOWN * 0.72)
    return VGroup(card, heading, sub, paths, start_dot, symbol)


class BeamSearchCore(Scene):
    def setup(self):
        self.camera.background_color = SKY
        self.elapsed = 0.0

    def tplay(self, *animations, run_time: float = 1.0, **kwargs) -> None:
        self.play(*animations, run_time=run_time, **kwargs)
        self.elapsed += run_time

    def twait(self, duration: float) -> None:
        self.wait(duration)
        self.elapsed += duration

    def visit_tree_node(
        self,
        graph: SearchTreeGraph,
        node_id: str,
        previous: str | None,
        accent,
    ) -> list:
        animations = [graph.cursor.animate.move_to(graph._node_center(node_id))]
        if previous is not None:
            edge = graph.edge_mobs.get((previous, node_id))
            if edge is not None:
                animations.append(
                    edge.animate.set_color(accent).set_stroke(
                        width=max(2.8, 3.6 * graph.scale),
                        opacity=1,
                    )
                )

        body = graph.node_mobs[node_id][0]
        node_data = graph.nodes[node_id]
        if node_data.get("leaf") == "dead":
            animations.append(body.animate.set_fill(DANGER, opacity=1))
        elif node_data.get("leaf") == "solution":
            animations.append(body.animate.set_fill(accent, opacity=1))
        else:
            animations.append(body.animate.set_fill(accent, opacity=0.82))

        if len(graph.node_mobs[node_id]) > 1:
            animations.append(graph.node_mobs[node_id][1].animate.set_opacity(1))
        animations.append(body.animate.set_opacity(1))
        return animations

    def highlight_tree_path(
        self,
        graph: SearchTreeGraph,
        leaf_id: str,
        accent,
        caption: str,
    ) -> Text:
        path = graph.path_to(leaf_id)
        animations = []
        for node in path:
            body = graph.node_mobs[node][0]
            animations.append(
                body.animate.set_fill(accent, opacity=1).set_stroke(accent, width=3.2)
            )
            if len(graph.node_mobs[node]) > 1:
                animations.append(graph.node_mobs[node][1].animate.set_opacity(1))
        for start, end in zip(path, path[1:]):
            edge = graph.edge_mobs[(start, end)]
            animations.append(
                edge.animate.set_color(accent).set_stroke(width=max(4.5, 5.5 * graph.scale), opacity=1)
            )

        caption_mob = label(caption, size=24, color=accent)
        caption_mob.next_to(graph.group, DOWN, buff=0.12)
        animations.append(FadeIn(caption_mob, shift=UP * 0.06))
        self.tplay(*animations, run_time=0.95)
        return caption_mob

    def soften_tree_path(
        self,
        graph: SearchTreeGraph,
        leaf_id: str,
        accent,
    ) -> None:
        path = graph.path_to(leaf_id)
        animations = []
        for node in path:
            body = graph.node_mobs[node][0]
            animations.append(body.animate.set_stroke(INK, width=2))
        for start, end in zip(path, path[1:]):
            edge = graph.edge_mobs[(start, end)]
            animations.append(
                edge.animate.set_color(accent).set_stroke(width=max(2.2, 2.8 * graph.scale), opacity=0.85)
            )
        self.tplay(*animations, run_time=0.35)

    def animate_dual_tree_search(
        self,
        dfs_graph: SearchTreeGraph,
        bfs_graph: SearchTreeGraph,
        dfs_order: list[str],
        bfs_order: list[str],
        dfs_solution: str,
        bfs_solution: str,
        step_time: float = 0.48,
    ) -> tuple[list, list]:
        dfs_prev: str | None = None
        bfs_prev: str | None = None
        dfs_captions: list = []
        bfs_captions: list = []
        total_steps = max(len(dfs_order), len(bfs_order))

        for index in range(total_steps):
            animations = []
            dfs_leaf: str | None = None
            bfs_leaf: str | None = None

            if index < len(dfs_order):
                dfs_node = dfs_order[index]
                animations.extend(
                    self.visit_tree_node(dfs_graph, dfs_node, dfs_prev, DANGER)
                )
                if dfs_graph.nodes[dfs_node].get("leaf"):
                    dfs_leaf = dfs_node
                dfs_prev = dfs_node

            if index < len(bfs_order):
                bfs_node = bfs_order[index]
                animations.extend(
                    self.visit_tree_node(bfs_graph, bfs_node, bfs_prev, KEEP)
                )
                if bfs_graph.nodes[bfs_node].get("leaf"):
                    bfs_leaf = bfs_node
                bfs_prev = bfs_node

            if animations:
                self.tplay(AnimationGroup(*animations, lag_ratio=0), run_time=step_time)

            if dfs_leaf is not None:
                steps = len(dfs_graph.path_to(dfs_leaf)) - 1
                if dfs_graph.nodes[dfs_leaf].get("leaf") == "dead":
                    caption = self.highlight_tree_path(
                        dfs_graph,
                        dfs_leaf,
                        DANGER,
                        f"{steps} 步 · 死路",
                    )
                    dfs_captions.append(caption)
                    self.soften_tree_path(dfs_graph, dfs_leaf, DANGER)
                else:
                    caption = self.highlight_tree_path(
                        dfs_graph,
                        dfs_leaf,
                        DANGER,
                        f"{steps} 步 · 首次解法",
                    )
                    dfs_captions.append(caption)

            if bfs_leaf is not None:
                steps = len(bfs_graph.path_to(bfs_leaf)) - 1
                if bfs_graph.nodes[bfs_leaf].get("leaf") == "dead":
                    caption = self.highlight_tree_path(
                        bfs_graph,
                        bfs_leaf,
                        DANGER,
                        f"{steps} 步 · 死路",
                    )
                    bfs_captions.append(caption)
                    self.soften_tree_path(bfs_graph, bfs_leaf, DANGER)
                else:
                    suffix = "（最少）" if bfs_leaf == bfs_solution else ""
                    caption = self.highlight_tree_path(
                        bfs_graph,
                        bfs_leaf,
                        KEEP,
                        f"{steps} 步 · 首次解法{suffix}",
                    )
                    bfs_captions.append(caption)

        return dfs_captions, bfs_captions

    def construct(self):
        background = make_background()
        self.add(background)

        # First explain how the bird puzzle becomes a stack-search problem.
        model_title = label("鸟类消除游戏，如何建模？", size=48).to_edge(UP, buff=0.34)
        model_bar = Line(
            model_title.get_left() + DOWN * 0.22,
            model_title.get_right() + DOWN * 0.22,
            color=SKY_DEEP,
            stroke_width=5,
        )
        model_hint = label("树枝  →  栈", size=34, color=KEEP).next_to(
            model_title, DOWN, buff=0.38
        )
        self.tplay(
            FadeIn(model_title, shift=DOWN * 0.16),
            Create(model_bar),
            FadeIn(model_hint, shift=UP * 0.10),
            run_time=1.0,
        )
        self.twait(0.4)

        left_center = np.array([-2.30, 0.45, 0.0])
        right_center = np.array([2.30, 0.45, 0.0])
        left_stack, left_branch, left_birds, _ = make_stack_example(
            left_center, "left", (0, 1, 2, 2)
        )
        right_stack, right_branch, _, right_slots = make_stack_example(
            right_center, "right", ()
        )
        stack_diagram = VGroup(left_stack, right_stack)
        self.tplay(
            LaggedStart(
                FadeIn(left_branch, shift=UP * 0.10),
                FadeIn(right_branch, shift=UP * 0.10),
                lag_ratio=0.12,
            ),
            LaggedStart(*[FadeIn(bird, scale=0.75) for bird in left_birds], lag_ratio=0.08),
            run_time=1.4,
        )
        self.twait(0.5)

        stack_caption = label("一根树枝 = 一个栈", size=34).move_to(DOWN * 0.72)
        fixed_tag = label("栈底", size=24, color=MUTED, weight="NORMAL").move_to(
            left_branch[0].get_start() + DOWN * 0.42
        )
        top_tag = label("栈顶", size=24, color=KEEP).move_to(
            left_branch[0].get_end() + DOWN * 0.42
        )
        top_arrow = Arrow(
            top_tag.get_top() + UP * 0.02,
            left_branch[0].get_end() + UP * 0.05,
            buff=0.05,
            color=KEEP,
            stroke_width=3,
            tip_length=0.13,
        )
        self.tplay(
            FadeIn(stack_caption, shift=UP * 0.10),
            FadeIn(fixed_tag),
            FadeIn(top_tag),
            Create(top_arrow),
            run_time=0.9,
        )
        self.twait(0.6)

        rule_line = label("先进后出：每次只移动栈顶同类鸟", size=34, color=INK).move_to(
            DOWN * 1.55
        )
        top_same = VGroup(*left_birds[-2:])
        top_highlight = RoundedRectangle(
            width=top_same.width + 0.22,
            height=top_same.height + 0.20,
            corner_radius=0.20,
            stroke_color=GOLD,
            stroke_width=5,
            fill_opacity=0,
        ).move_to(top_same)
        self.tplay(
            FadeIn(rule_line, shift=UP * 0.10),
            Create(top_highlight),
            run_time=0.8,
        )
        self.twait(0.5)

        moving_birds = list(left_birds[-2:])
        flights = [
            MoveAlongPath(
                bird,
                ArcBetweenPoints(bird.get_center(), right_slots[index], angle=-PI / 3),
                rate_func=ease_in_out_cubic,
            )
            for index, bird in enumerate(moving_birds)
        ]
        self.tplay(
            AnimationGroup(*flights, lag_ratio=0.10),
            FadeOut(top_highlight),
            FadeOut(top_arrow),
            run_time=1.3,
        )
        self.twait(0.6)

        goal_left, _, _, _ = make_stack_example(left_center, "left", (0, 0, 0, 0))
        goal_right, _, _, _ = make_stack_example(right_center, "right", ())
        goal_diagram = VGroup(goal_left, goal_right)
        goal_title = label("目标：每根树枝都是同类鸟，或者为空", size=40, color=KEEP).move_to(
            UP * 2.30
        )
        goal_marks = VGroup(
            label("✓ 同类", size=30, color=KEEP).move_to(left_center + UP * 1.22),
            label("✓ 空", size=30, color=KEEP).move_to(right_center + UP * 1.22),
        )
        self.tplay(
            FadeOut(model_hint),
            FadeOut(stack_diagram),
            FadeOut(stack_caption),
            FadeOut(fixed_tag),
            FadeOut(top_tag),
            FadeOut(rule_line),
            FadeIn(goal_diagram, scale=0.92),
            FadeIn(goal_title, shift=UP * 0.10),
            LaggedStart(*[FadeIn(mark, shift=UP * 0.08) for mark in goal_marks], lag_ratio=0.15),
            run_time=1.0,
        )
        self.twait(1.0)
        self.tplay(
            FadeOut(model_title),
            FadeOut(model_bar),
            FadeOut(goal_title),
            FadeOut(goal_diagram),
            FadeOut(goal_marks),
            run_time=0.8,
        )

        title = label("问题解决方案：状态搜索", size=46).to_edge(UP, buff=0.34)
        title_bar = Line(
            title.get_left() + DOWN * 0.22,
            title.get_right() + DOWN * 0.22,
            color=SKY_DEEP,
            stroke_width=5,
        )
        search_hint = label("每一步移动 → 一个新状态；叶子节点 = 终局解法", size=28, color=MUTED, weight="NORMAL")
        search_hint.next_to(title, DOWN, buff=0.34)
        self.tplay(
            FadeIn(title, shift=DOWN * 0.16),
            Create(title_bar),
            FadeIn(search_hint, shift=UP * 0.08),
            run_time=1.0,
        )
        self.twait(0.30)

        tree_scale = 0.54
        dfs_graph = SearchTreeGraph(scale=tree_scale, shift=np.array([-3.15, -0.05, 0.0]))
        bfs_graph = SearchTreeGraph(scale=tree_scale, shift=np.array([3.15, -0.05, 0.0]))
        dfs_group = dfs_graph.build()
        bfs_group = bfs_graph.build()
        divider = DashedLine(UP * 2.35, DOWN * 2.55, color=MUTED, dash_length=0.12)
        panel_titles = VGroup(
            label("深度优先 DFS", size=30, color=DANGER).move_to(np.array([-3.15, 2.35, 0.0])),
            label("宽度优先 BFS", size=30, color=KEEP).move_to(np.array([3.15, 2.35, 0.0])),
        )
        self.add(dfs_graph.cursor, bfs_graph.cursor)
        dfs_graph.cursor.set_opacity(1)
        bfs_graph.cursor.set_opacity(1)
        leaf_legend = VGroup(
            make_badge("✓ 解法", KEEP),
            make_badge("× 死路", DANGER),
        ).arrange(RIGHT, buff=0.42).to_edge(DOWN, buff=0.42)
        self.tplay(
            Create(divider),
            FadeIn(panel_titles, shift=DOWN * 0.08),
            Create(dfs_group[0]),
            Create(bfs_group[0]),
            LaggedStart(
                *[FadeIn(node, scale=0.85) for node in dfs_group[1]],
                *[FadeIn(node, scale=0.85) for node in bfs_group[1]],
                lag_ratio=0.03,
            ),
            FadeIn(leaf_legend, shift=UP * 0.08),
            run_time=1.45,
        )
        self.twait(0.35)
        self.tplay(FadeOut(leaf_legend), run_time=0.35)

        dfs_order_full = SearchTreeGraph.dfs_order(dfs_graph.nodes)
        bfs_order_full = SearchTreeGraph.bfs_order(bfs_graph.nodes)
        dfs_solution = dfs_graph.first_solution(dfs_order_full)
        bfs_solution = bfs_graph.first_solution(bfs_order_full)
        dfs_order = dfs_order_full[: dfs_order_full.index(dfs_solution) + 1]
        bfs_order = bfs_order_full[: bfs_order_full.index(bfs_solution) + 1]

        dfs_graph.cursor.move_to(dfs_graph._node_center("R"))
        bfs_graph.cursor.move_to(bfs_graph._node_center("R"))
        dual_note = label("同一棵搜索树，两种算法同步逐步展开", size=26, color=MUTED, weight="NORMAL")
        dual_note.next_to(search_hint, DOWN, buff=0.16)
        self.tplay(FadeIn(dual_note, shift=UP * 0.06), run_time=0.45)

        dfs_captions, bfs_captions = self.animate_dual_tree_search(
            dfs_graph,
            bfs_graph,
            dfs_order,
            bfs_order,
            dfs_solution,
            bfs_solution,
            step_time=0.48,
        )
        self.twait(1.0)
        self.tplay(
            FadeOut(dfs_group),
            FadeOut(bfs_group),
            FadeOut(divider),
            FadeOut(panel_titles),
            FadeOut(dfs_graph.cursor),
            FadeOut(bfs_graph.cursor),
            FadeOut(dual_note),
            FadeOut(search_hint),
            FadeOut(*dfs_captions),
            FadeOut(*bfs_captions),
            run_time=0.65,
        )

        timer_title = label("游戏有时间限制", size=46, color=DANGER).to_edge(UP, buff=0.34)
        timer_bar = Line(
            timer_title.get_left() + DOWN * 0.22,
            timer_title.get_right() + DOWN * 0.22,
            color=DANGER,
            stroke_width=5,
        )
        timer_frame = RoundedRectangle(
            width=4.8,
            height=0.62,
            corner_radius=0.16,
            stroke_color=DANGER,
            stroke_width=3,
            fill_color=WHITE,
            fill_opacity=0.88,
        ).move_to(UP * 0.55)
        timer_fill = Rectangle(
            width=3.2,
            height=0.38,
            stroke_width=0,
            fill_color=DANGER,
            fill_opacity=0.85,
        ).move_to(timer_frame.get_center() + LEFT * 0.55)
        timer_words = label("操作越少 → 用时越短 → 不易超时", size=34, color=INK).move_to(DOWN * 0.35)
        bfs_choice = label("BFS 保证最先找到的解 = 最少步数", size=36, color=KEEP).move_to(DOWN * 1.35)
        bfs_box = RoundedRectangle(
            width=bfs_choice.width + 0.55,
            height=bfs_choice.height + 0.38,
            corner_radius=0.18,
            stroke_color=KEEP,
            stroke_width=3,
            fill_color=KEEP_LIGHT,
            fill_opacity=0.35,
        ).move_to(bfs_choice)
        self.tplay(
            ReplacementTransform(title, timer_title),
            ReplacementTransform(title_bar, timer_bar),
            FadeIn(timer_frame),
            FadeIn(timer_fill, shift=RIGHT * 0.12),
            FadeIn(timer_words, shift=UP * 0.10),
            run_time=1.05,
        )
        self.twait(0.45)
        self.tplay(FadeIn(bfs_box), FadeIn(bfs_choice, shift=UP * 0.10), run_time=0.85)
        self.twait(0.75)
        self.tplay(
            FadeOut(timer_frame),
            FadeOut(timer_fill),
            FadeOut(timer_words),
            FadeOut(bfs_box),
            FadeOut(bfs_choice),
            run_time=0.55,
        )

        prune_title = label("实现加速：重复分支剪枝", size=44).to_edge(UP, buff=0.34)
        prune_bar = Line(
            prune_title.get_left() + DOWN * 0.22,
            prune_title.get_right() + DOWN * 0.22,
            color=GOLD,
            stroke_width=5,
        )
        pruning_demo = make_pruning_demo()
        prune_note = label(
            "生成后继时：if key in seen: continue",
            size=28,
            color=INK,
            weight="NORMAL",
        ).to_edge(DOWN, buff=0.42)
        self.tplay(
            ReplacementTransform(timer_title, prune_title),
            ReplacementTransform(timer_bar, prune_bar),
            LaggedStart(*[FadeIn(item, shift=UP * 0.10) for item in pruning_demo], lag_ratio=0.12),
            run_time=1.35,
        )
        self.tplay(FadeIn(prune_note, shift=UP * 0.08), run_time=0.55)
        self.twait(0.65)
        self.tplay(
            FadeOut(pruning_demo),
            FadeOut(prune_note),
            run_time=0.55,
        )

        beam_title = label("进一步：Beam Search 平衡速度与搜索空间", size=40, color=KEEP).to_edge(
            UP, buff=0.34
        )
        beam_bar = Line(
            beam_title.get_left() + DOWN * 0.22,
            beam_title.get_right() + DOWN * 0.22,
            color=KEEP,
            stroke_width=5,
        )
        beam_badge = make_badge("BFS + 束宽 3", KEEP).to_corner(UR, buff=0.42)
        self.tplay(
            ReplacementTransform(prune_title, beam_title),
            ReplacementTransform(prune_bar, beam_bar),
            FadeIn(beam_badge, shift=LEFT * 0.18),
            run_time=0.75,
        )
        title = beam_title
        title_bar = beam_bar
        self.twait(0.35)

        # Show the first expansion as four concrete candidate states.
        candidate_moves = (
            Move(2, 4, 2, False),
            Move(0, 4, 1, False),
            Move(1, 4, 1, False),
            Move(3, 4, 1, False),
        )
        candidate_states = [INITIAL_STATE.apply(move) for move in candidate_moves]
        root_card = SnapshotCard(INITIAL_STATE).scale(0.72).move_to(UP * 1.95)
        candidate_cards = VGroup(
            *[SnapshotCard(state) for state in candidate_states]
        ).arrange(RIGHT, buff=0.32).move_to(DOWN * 0.73)
        connectors = VGroup(
            *[
                Arrow(
                    root_card.get_bottom(),
                    card.get_top(),
                    buff=0.12,
                    color=MUTED,
                    stroke_width=2.2,
                    tip_length=0.13,
                )
                for card in candidate_cards
            ]
        )
        phase = make_badge("展开", INK).to_corner(UR, buff=0.42)
        self.tplay(
            ReplacementTransform(beam_badge, phase),
            FadeIn(root_card, scale=0.8),
            LaggedStart(*[Create(connector) for connector in connectors], lag_ratio=0.08),
            LaggedStart(*[FadeIn(card, shift=UP * 0.18) for card in candidate_cards], lag_ratio=0.1),
            run_time=2.0,
        )
        self.twait(0.55)

        score_phase = make_badge("评分", GOLD).to_corner(UR, buff=0.42)
        rank_badges = VGroup()
        for index, card in enumerate(candidate_cards):
            circle = Circle(
                radius=0.22,
                fill_color=GOLD if index < 3 else MUTED,
                fill_opacity=1,
                stroke_color=WHITE,
                stroke_width=2,
            ).move_to(card.get_corner(UR) + LEFT * 0.23 + DOWN * 0.23)
            number = label(str(index + 1), size=23, color=WHITE).move_to(circle)
            rank_badges.add(VGroup(circle, number))
        self.tplay(
            ReplacementTransform(phase, score_phase),
            LaggedStart(*[GrowFromCenter(badge) for badge in rank_badges], lag_ratio=0.12),
            candidate_cards[0].animate.shift(UP * 0.13),
            candidate_cards[1].animate.shift(UP * 0.09),
            candidate_cards[2].animate.shift(UP * 0.05),
            run_time=1.25,
        )
        self.twait(0.7)

        keep_phase = make_badge("保留 3 个", KEEP).to_corner(UR, buff=0.42)
        drop_cross = Cross(candidate_cards[3], stroke_color=DANGER, stroke_width=5)
        keep_glows = VGroup(
            *[
                RoundedRectangle(
                    width=card.width + 0.12,
                    height=card.height + 0.12,
                    corner_radius=0.22,
                    stroke_color=KEEP,
                    stroke_width=5,
                    fill_opacity=0,
                ).move_to(card)
                for card in candidate_cards[:3]
            ]
        )
        self.tplay(
            ReplacementTransform(score_phase, keep_phase),
            LaggedStart(*[Create(glow) for glow in keep_glows], lag_ratio=0.12),
            candidate_cards[3].animate.set_opacity(0.2).scale(0.88),
            FadeIn(drop_cross),
            run_time=1.55,
        )
        self.twait(0.85)

        # A second real expansion shows that the same cycle repeats.
        kept_states = candidate_states[:3]
        next_candidates, next_survivors = next_beam(kept_states, width=3)
        top_cards = VGroup(*[candidate_cards[index].copy() for index in range(3)])
        for index, card in enumerate(top_cards):
            card.scale(0.70).move_to(np.array([-3.7 + index * 3.7, 1.52, 0.0]))

        child_states = next_candidates[:9]
        child_cards = VGroup(*[SnapshotCard(state).scale(0.48) for state in child_states])
        child_cards.arrange(RIGHT, buff=0.11).move_to(DOWN * 1.08)
        child_connectors = VGroup()
        for index, card in enumerate(child_cards):
            parent = top_cards[min(index // 3, 2)]
            child_connectors.add(
                DashedLine(
                    parent.get_bottom(),
                    card.get_top(),
                    dash_length=0.08,
                    color=MUTED,
                    stroke_width=1.5,
                )
            )

        repeat_phase = make_badge("重复", INK).to_corner(UR, buff=0.42)
        self.tplay(
            FadeOut(root_card),
            FadeOut(connectors),
            FadeOut(candidate_cards),
            FadeOut(rank_badges),
            FadeOut(keep_glows),
            FadeOut(drop_cross),
            ReplacementTransform(keep_phase, repeat_phase),
            LaggedStart(*[FadeIn(card, shift=UP * 0.12) for card in top_cards], lag_ratio=0.10),
            run_time=1.35,
        )
        self.tplay(
            LaggedStart(*[Create(line) for line in child_connectors], lag_ratio=0.03),
            LaggedStart(*[FadeIn(card, scale=0.78) for card in child_cards], lag_ratio=0.04),
            run_time=1.75,
        )

        survivor_keys = {state.canonical_key() for state in next_survivors}
        survivor_glows = VGroup()
        fade_animations = []
        for card, state in zip(child_cards, child_states):
            if state.canonical_key() in survivor_keys:
                survivor_glows.add(
                    RoundedRectangle(
                        width=card.width + 0.08,
                        height=card.height + 0.08,
                        corner_radius=0.12,
                        stroke_color=KEEP,
                        stroke_width=4,
                        fill_opacity=0,
                    ).move_to(card)
                )
            else:
                fade_animations.append(card.animate.set_opacity(0.16))
        self.tplay(
            LaggedStart(*[Create(glow) for glow in survivor_glows], lag_ratio=0.12),
            *fade_animations,
            run_time=1.25,
        )
        cycle_words = VGroup(
            label("展开", size=31),
            label("评分", size=31, color=GOLD),
            label("保留", size=31, color=KEEP),
        ).arrange(RIGHT, buff=0.72).move_to(DOWN * 2.55)
        cycle_arrows = VGroup(
            Arrow(cycle_words[0].get_right(), cycle_words[1].get_left(), buff=0.12, color=MUTED),
            Arrow(cycle_words[1].get_right(), cycle_words[2].get_left(), buff=0.12, color=MUTED),
        )
        self.tplay(
            LaggedStart(*[FadeIn(word, shift=UP * 0.10) for word in cycle_words], lag_ratio=0.16),
            LaggedStart(*[Create(arrow) for arrow in cycle_arrows], lag_ratio=0.15),
            run_time=1.05,
        )
        self.twait(0.8)

        # Return to the full board and play the verified twelve-move solution.
        route_title = label("找到能走通的路线", size=48, color=KEEP).to_edge(UP, buff=0.34)
        route_bar = Line(
            route_title.get_left() + DOWN * 0.22,
            route_title.get_right() + DOWN * 0.22,
            color=KEEP,
            stroke_width=5,
        )
        solution_board = BirdBoard(INITIAL_STATE)
        tree_group = VGroup(
            top_cards,
            child_connectors,
            child_cards,
            survivor_glows,
            cycle_words,
            cycle_arrows,
            repeat_phase,
        )
        self.tplay(
            FadeOut(tree_group),
            ReplacementTransform(title, route_title),
            ReplacementTransform(title_bar, route_bar),
            FadeIn(solution_board.group, scale=0.86),
            run_time=1.55,
        )
        title = route_title
        title_bar = route_bar
        self.twait(0.45)

        for move in SOLUTION_MOVES:
            solution_board.move_animation(
                self,
                move,
                move_time=0.58,
                completion_time=0.32,
            )

        solved = label("全部消除", size=58, color=KEEP)
        solved_bg = RoundedRectangle(
            width=solved.width + 0.85,
            height=solved.height + 0.48,
            corner_radius=0.28,
            fill_color=WHITE,
            fill_opacity=0.92,
            stroke_color=KEEP,
            stroke_width=3,
        )
        solved_group = VGroup(solved_bg, solved)
        confetti = VGroup()
        confetti_colors = (KEEP, GOLD, DANGER, BIRD_COLORS[0], BIRD_COLORS[3])
        for index in range(22):
            angle = 2 * PI * index / 22
            radius = 1.25 + 0.35 * (index % 3)
            piece = Star(
                n=5,
                outer_radius=0.10,
                inner_radius=0.045,
                fill_color=confetti_colors[index % len(confetti_colors)],
                fill_opacity=1,
                stroke_width=0,
            ).move_to(np.array([np.cos(angle) * radius, np.sin(angle) * radius, 0]))
            confetti.add(piece)
        self.tplay(
            GrowFromCenter(solved_group),
            LaggedStart(*[GrowFromCenter(piece) for piece in confetti], lag_ratio=0.025),
            run_time=1.25,
            rate_func=ease_out_back,
        )
        self.twait(1.05)

        # End with the algorithm stack summary.
        comparison_title = label("求解策略组合", size=48).to_edge(UP, buff=0.34)
        comparison_bar = Line(
            comparison_title.get_left() + DOWN * 0.22,
            comparison_title.get_right() + DOWN * 0.22,
            color=SKY_DEEP,
            stroke_width=5,
        )
        comparisons = VGroup(
            comparison_card("BFS", "最少步数保证", KEEP, 3, True),
            comparison_card("剪枝", "跳过重复状态", GOLD, 2, True),
            comparison_card("Beam", "速度与空间平衡", INK, 3, True),
        ).arrange(RIGHT, buff=0.48).move_to(DOWN * 0.30)
        self.tplay(
            FadeOut(solution_board.group),
            FadeOut(solved_group),
            FadeOut(confetti),
            FadeOut(repeat_phase),
            ReplacementTransform(title, comparison_title),
            ReplacementTransform(title_bar, comparison_bar),
            LaggedStart(*[FadeIn(card, shift=UP * 0.18) for card in comparisons], lag_ratio=0.14),
            run_time=1.6,
        )
        self.twait(1.2)

        final_words = label("BFS + 剪枝 + Beam Search", size=52, color=INK)
        final_name = label("在时限内找到可行解", size=36, color=KEEP).next_to(
            final_words, DOWN, buff=0.30
        )
        final_line = Line(
            final_words.get_left(),
            final_words.get_right(),
            color=KEEP,
            stroke_width=7,
        ).next_to(final_words, UP, buff=0.25)
        self.tplay(
            FadeOut(comparisons),
            FadeOut(comparison_title),
            FadeOut(comparison_bar),
            FadeIn(final_words, shift=UP * 0.18),
            Create(final_line),
            run_time=1.0,
        )
        self.tplay(FadeIn(final_name, shift=UP * 0.10), run_time=0.55)

        remaining = TARGET_DURATION - self.elapsed
        if remaining < -0.01:
            raise RuntimeError(f"Timeline is {self.elapsed:.2f}s, longer than {TARGET_DURATION}s")
        if remaining > 0:
            self.twait(remaining)

        print(f"TIMELINE_DURATION={self.elapsed:.2f}")
