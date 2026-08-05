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


TARGET_DURATION = 75.0
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

    def construct(self):
        background = make_background()
        self.add(background)

        title = label("只看眼前，会发生什么？", size=48).to_edge(UP, buff=0.34)
        title_bar = Line(
            title.get_left() + DOWN * 0.22,
            title.get_right() + DOWN * 0.22,
            color=SKY_DEEP,
            stroke_width=5,
        )
        self.tplay(FadeIn(title, shift=DOWN * 0.16), Create(title_bar), run_time=1.2)
        self.twait(1.0)

        board = BirdBoard(INITIAL_STATE)
        self.tplay(
            LaggedStart(*[FadeIn(branch, shift=UP * 0.12) for branch in board.branch_groups], lag_ratio=0.08),
            LaggedStart(
                *[FadeIn(bird, scale=0.72) for branch in board.birds for bird in branch],
                lag_ratio=0.025,
            ),
            run_time=2.2,
        )
        self.twait(0.8)

        greedy_badge = make_badge("束宽 1", DANGER).to_corner(UR, buff=0.42)
        self.tplay(FadeIn(greedy_badge, shift=LEFT * 0.18), run_time=0.8)
        self.twait(0.7)

        aa_focus = RoundedRectangle(
            width=1.55,
            height=0.95,
            corner_radius=0.22,
            stroke_color=GOLD,
            stroke_width=5,
            fill_opacity=0,
        ).move_to(board.positions[2] + RIGHT * 0.82 + UP * 0.27)
        cue = label("看起来最好", size=30, color=INK).next_to(aa_focus, UP, buff=0.13)
        self.tplay(Create(aa_focus), FadeIn(cue, shift=UP * 0.08), run_time=0.8)
        self.twait(0.6)
        self.tplay(FadeOut(aa_focus), FadeOut(cue), run_time=0.35)

        state_after_first = INITIAL_STATE.apply(GREEDY_MOVES[0])
        board.move_animation(self, GREEDY_MOVES[0], move_time=1.65)
        self.twait(0.55)
        board.move_animation(self, GREEDY_MOVES[1], move_time=1.35)
        self.twait(0.55)

        lock_overlay = VGroup()
        for center in board.positions:
            lock_overlay.add(
                Circle(
                    radius=0.34,
                    fill_color=DANGER,
                    fill_opacity=0.10,
                    stroke_color=DANGER,
                    stroke_width=2.8,
                ).move_to(center + UP * 0.35)
            )
        dead_cross = Cross(stroke_color=DANGER, stroke_width=12).scale(0.82)
        dead_text = label("卡住了", size=50, color=DANGER).next_to(dead_cross, DOWN, buff=0.24)
        self.tplay(
            LaggedStart(*[FadeIn(circle) for circle in lock_overlay], lag_ratio=0.05),
            GrowFromCenter(dead_cross),
            FadeIn(dead_text, shift=UP * 0.15),
            board.group.animate.shift(LEFT * 0.08),
            run_time=1.1,
            rate_func=ease_out_back,
        )
        self.tplay(board.group.animate.shift(RIGHT * 0.16), run_time=0.22)
        self.tplay(board.group.animate.shift(LEFT * 0.08), run_time=0.22)
        self.twait(1.5)

        rewind = make_badge("倒放", GOLD).move_to(UP * 3.05)
        rewind_arrow = Arrow(
            rewind.get_left() + LEFT * 0.25,
            rewind.get_right() + RIGHT * 0.25,
            color=GOLD,
            stroke_width=6,
        ).rotate(PI)
        self.tplay(
            FadeOut(lock_overlay),
            FadeOut(dead_cross),
            FadeOut(dead_text),
            FadeIn(rewind, scale=0.8),
            Create(rewind_arrow),
            run_time=0.75,
        )
        board.reverse_animation(self, GREEDY_MOVES[1], state_after_first, run_time=1.05)
        board.reverse_animation(self, GREEDY_MOVES[0], INITIAL_STATE, run_time=1.30)
        self.tplay(FadeOut(rewind), FadeOut(rewind_arrow), run_time=0.45)
        self.twait(0.5)

        beam_badge = make_badge("束宽 3", KEEP).to_corner(UR, buff=0.42)
        new_title = label("多保留几个未来", size=48).to_edge(UP, buff=0.34)
        new_title_bar = Line(
            new_title.get_left() + DOWN * 0.22,
            new_title.get_right() + DOWN * 0.22,
            color=KEEP,
            stroke_width=5,
        )
        self.tplay(
            ReplacementTransform(greedy_badge, beam_badge),
            ReplacementTransform(title, new_title),
            ReplacementTransform(title_bar, new_title_bar),
            run_time=0.9,
        )
        title = new_title
        title_bar = new_title_bar
        self.twait(0.75)

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
            FadeOut(board.group),
            ReplacementTransform(beam_badge, phase),
            FadeIn(root_card, scale=0.8),
            LaggedStart(*[Create(connector) for connector in connectors], lag_ratio=0.08),
            LaggedStart(*[FadeIn(card, shift=UP * 0.18) for card in candidate_cards], lag_ratio=0.1),
            run_time=2.3,
        )
        self.twait(0.8)

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
                move_time=0.92,
                completion_time=0.48,
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

        # End with the core trade-off, using only three short labels.
        comparison_title = label("一次保留多少个未来？", size=48).to_edge(UP, buff=0.34)
        comparison_bar = Line(
            comparison_title.get_left() + DOWN * 0.22,
            comparison_title.get_right() + DOWN * 0.22,
            color=SKY_DEEP,
            stroke_width=5,
        )
        comparisons = VGroup(
            comparison_card("1", "容易走进死路", DANGER, 1, False),
            comparison_card("3", "速度与探索的平衡", KEEP, 3, True),
            comparison_card("全部", "更全面，也更慢", GOLD, 7, True),
        ).arrange(RIGHT, buff=0.48).move_to(DOWN * 0.30)
        self.tplay(
            FadeOut(solution_board.group),
            FadeOut(solved_group),
            FadeOut(confetti),
            ReplacementTransform(title, comparison_title),
            ReplacementTransform(title_bar, comparison_bar),
            LaggedStart(*[FadeIn(card, shift=UP * 0.18) for card in comparisons], lag_ratio=0.14),
            run_time=2.0,
        )
        self.twait(2.2)

        final_words = label("多考虑几个未来", size=66, color=INK)
        final_name = label("Beam Search", size=39, color=KEEP).next_to(final_words, DOWN, buff=0.30)
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
            FadeOut(beam_badge),
            FadeIn(final_words, shift=UP * 0.18),
            Create(final_line),
            run_time=1.15,
        )
        self.tplay(FadeIn(final_name, shift=UP * 0.10), run_time=0.65)

        remaining = TARGET_DURATION - self.elapsed
        if remaining < -0.01:
            raise RuntimeError(f"Timeline is {self.elapsed:.2f}s, longer than {TARGET_DURATION}s")
        if remaining > 0:
            self.twait(remaining)

        print(f"TIMELINE_DURATION={self.elapsed:.2f}")
