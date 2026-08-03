from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from .controller import (
    AdbController,
    DeviceController,
    DeviceError,
    WdaController,
)
from .model import REMOVED, BoardState, Branch, Move
from .solution_html import write_solution_animation
from .solver import BeamSolver, SolveResult
from .vision import BoardRecognizer, DetectedBranch, RecognitionError, RecognitionResult


def _symbol(value: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return alphabet[value] if value < len(alphabet) else str(value)


def _format_board(result: RecognitionResult) -> str:
    lines = [
        f"image={result.image_size[0]}x{result.image_size[1]}  "
        f"branches={len(result.branches)}  birds={result.state.bird_count}  "
        f"types={result.type_count}",
        f"cluster_sizes={list(result.cluster_sizes)}  "
        f"silhouette={result.silhouette if result.silhouette is not None else 'n/a'}",
        "branch order: fixed/base end -> movable/outer end",
    ]
    side_numbers = {"left": 0, "right": 0}
    for index, branch in enumerate(result.branches):
        side_numbers[branch.side] += 1
        name = f"{branch.side[0].upper()}{side_numbers[branch.side]:02d}"
        birds = " ".join(_symbol(value) for value in branch.birds) or "(empty)"
        lines.append(
            f"  #{index:02d} {name} y={branch.branch_y:4d}: [{birds}]"
        )
    return "\n".join(lines)


def _format_solution(solution: SolveResult, limit: int | None = None) -> str:
    status = "solved" if solution.solved else "best effort"
    lines = [
        f"{status}: eliminate {solution.eliminated}/{solution.target} branches, "
        f"moves={len(solution.moves)}, explored={solution.explored_states}, "
        f"time={solution.elapsed_seconds:.2f}s"
    ]
    moves = solution.moves if limit is None else solution.moves[:limit]
    for number, move in enumerate(moves, 1):
        suffix = " -> eliminate" if move.completes_branch else ""
        lines.append(
            f"  {number:02d}. #{move.source:02d} -> #{move.destination:02d} "
            f"({move.count} bird{'s' if move.count != 1 else ''}){suffix}"
        )
    if limit is not None and len(solution.moves) > limit:
        lines.append(f"  ... {len(solution.moves) - limit} more moves")
    return "\n".join(lines)


def _recognizer(args: argparse.Namespace) -> BoardRecognizer:
    return BoardRecognizer(
        type_count=args.types,
        max_types=args.max_types,
    )


def _solver(args: argparse.Namespace) -> BeamSolver:
    return BeamSolver(
        beam_width=args.beam_width,
        max_depth=args.max_depth,
        time_limit=args.time_limit,
    )


def _controller(args: argparse.Namespace) -> DeviceController:
    if args.platform == "ios":
        return WdaController(
            base_url=args.wda_url,
            timeout=args.wda_timeout,
            session_id=args.wda_session_id,
            default_active_application=args.wda_default_active_application,
            quiescence_timeout=args.wda_quiescence_timeout,
        )
    return AdbController(args.adb, args.serial)


def _create_run_directory(root: Path = Path(".ios/runs")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index in range(1_000):
        suffix = "" if index == 0 else f"-{index:02d}"
        candidate = root / f"run-{timestamp}{suffix}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"Could not create a unique run directory under {root}")


def _save_play_screenshot(
    screenshot: Image.Image,
    run_directory: Path,
    filename: str,
    extra_directory: str | None,
) -> None:
    screenshot.save(run_directory / filename, compress_level=1)
    if extra_directory:
        directory = Path(extra_directory)
        directory.mkdir(parents=True, exist_ok=True)
        screenshot.save(directory / filename, compress_level=1)


def _prepare_manual_start(controller: DeviceController) -> None:
    print("正在预热设备会话和截图通道…")
    controller.capture()
    try:
        input(
            "\a准备完成。请现在开始游戏，然后回到终端按 Enter，"
            "程序将立即开始识别和操作："
        )
    except EOFError as exc:
        raise RuntimeError("等待开始确认失败：当前输入不是交互式终端") from exc


def _write_deferred_debug_reports(
    recognizer: BoardRecognizer,
    run_directory: Path,
) -> None:
    screenshots = sorted(run_directory.glob("turn-???.png"))
    if not screenshots:
        return

    print(f"\n游戏操作已结束，正在生成 {len(screenshots)} 份聚类调试报告…")
    failures = 0
    for screenshot in screenshots:
        debug_directory = run_directory / f"{screenshot.stem}-clusters"
        try:
            recognizer.read(screenshot, debug_dir=debug_directory)
        except RecognitionError as exc:
            failures += 1
            print(f"warning: 无法生成 {screenshot.name} 的调试报告：{exc}")
    if failures:
        print(f"调试报告生成完成，其中 {failures} 份失败。")
    else:
        print("聚类调试报告生成完成。")


def _recognition_summary(result: RecognitionResult) -> tuple[int, int]:
    return len(result.branches), result.state.bird_count


def _is_plausible_board_transition(
    previous: tuple[int, int],
    current: tuple[int, int],
) -> bool:
    previous_branches, previous_birds = previous
    current_branches, current_birds = current
    return current == previous or (
        current_branches == previous_branches - 1
        and current_birds == previous_birds - 4
    )


def _capture_game_board(
    controller: DeviceController,
    recognizer: BoardRecognizer,
    args: argparse.Namespace,
    run_directory: Path,
    turn_name: str,
    previous_summary: tuple[int, int] | None = None,
) -> tuple[Image.Image, RecognitionResult]:
    deadline = time.monotonic() + args.interruption_timeout
    interruption_index = 0
    waiting = False
    manual_prompted = False

    while True:
        screenshot = controller.capture_stable(
            interval=args.capture_interval,
            attempts=args.capture_attempts,
        )
        recognition: RecognitionResult | None = None
        has_board = recognizer.has_game_board(screenshot)
        if has_board:
            debug_directory = (
                run_directory / f"{turn_name}-clusters"
                if args.debug_reports == "live"
                else None
            )
            try:
                recognition = recognizer.read(
                    screenshot,
                    debug_dir=debug_directory,
                )
            except RecognitionError:
                _save_play_screenshot(
                    screenshot,
                    run_directory,
                    f"{turn_name}.png",
                    args.save_frames,
                )
                raise

        transition_rejected = (
            recognition is not None
            and previous_summary is not None
            and not _is_plausible_board_transition(
                previous_summary,
                _recognition_summary(recognition),
            )
        )
        if transition_rejected:
            has_board = False

        if has_board:
            _save_play_screenshot(
                screenshot,
                run_directory,
                f"{turn_name}.png",
                args.save_frames,
            )
            assert recognition is not None
            if waiting:
                print("已重新检测到游戏棋盘，继续操作。")
            return screenshot, recognition

        waiting = True
        interruption_index += 1
        filename = (
            f"{turn_name}-suspicious-board-{interruption_index:03d}.png"
            if transition_rejected
            else f"{turn_name}-interruption-{interruption_index:03d}.png"
        )
        _save_play_screenshot(
            screenshot,
            run_directory,
            filename,
            args.save_frames,
        )
        if not manual_prompted:
            if transition_rejected:
                assert recognition is not None and previous_summary is not None
                print(
                    "识别结果与上一轮变化幅度不合理："
                    f"{previous_summary} -> {_recognition_summary(recognition)}。"
                    "可能出现广告或遮罩；程序不会自动操作，将等待棋盘恢复。"
                )
            else:
                print(
                    "未检测到正常棋盘，可能出现广告或其他中断画面。"
                    "程序不会自动操作，请手动处理；程序会等待棋盘恢复。"
                )
            manual_prompted = True

        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"等待游戏棋盘恢复超时（{args.interruption_timeout:g} 秒）"
            )
        time.sleep(args.interruption_poll_interval)


def _click_point_for_contents(
    branch: DetectedBranch,
    contents: Branch,
) -> tuple[int, int]:
    if contents and contents != REMOVED:
        return branch.slots[len(contents) - 1]
    xs = [point[0] for point in branch.slots]
    return round(sum(xs) / len(xs)), branch.branch_y - 2


def _destination_click_point(
    branch: DetectedBranch,
    source: tuple[int, int],
) -> tuple[int, int]:
    candidates = tuple((x, branch.branch_y - 2) for x, _y in branch.slots)
    return max(
        candidates,
        key=lambda point: (point[0] - source[0]) ** 2
        + (point[1] - source[1]) ** 2,
    )


def _next_move_batch(moves: tuple[Move, ...], limit: int) -> tuple[Move, ...]:
    """Stop a fast batch immediately after its first branch elimination."""

    batch: list[Move] = []
    for move in moves[:limit]:
        batch.append(move)
        if move.completes_branch:
            break
    return tuple(batch)


def _physical_state_key(state: BoardState) -> tuple[Branch, ...]:
    """Preserve branch positions while ignoring arbitrary cluster label ids."""

    labels: dict[int, int] = {}
    next_label = 0
    normalized: list[Branch] = []
    for branch in state.branches:
        if branch == REMOVED:
            normalized.append(REMOVED)
            continue
        values: list[int] = []
        for bird in branch:
            if bird not in labels:
                labels[bird] = next_label
                next_label += 1
            values.append(labels[bird])
        normalized.append(tuple(values))
    return tuple(normalized)


def analyze(args: argparse.Namespace) -> int:
    debug_directory = args.debug_dir or args.image.with_name(
        f"{args.image.stem}-clusters"
    )
    recognition = _recognizer(args).read(args.image, debug_dir=debug_directory)
    debug_report = debug_directory / "index.html"
    if not args.json:
        print(f"debug_report={debug_report}")
    solution = _solver(args).solve(recognition.state)
    animation_path: Path | None = None
    if not args.no_html:
        animation_path = args.html_output or args.image.with_name(
            f"{args.image.stem}-solution.html"
        )
        write_solution_animation(
            recognition,
            solution,
            animation_path,
            source_name=args.image.name,
        )
    if args.json:
        payload = {
            "image_size": recognition.image_size,
            "branches": [
                {
                    "side": branch.side,
                    "branch_y": branch.branch_y,
                    "birds": list(branch.birds),
                    "click": branch.click_point(),
                }
                for branch in recognition.branches
            ],
            "type_count": recognition.type_count,
            "cluster_sizes": recognition.cluster_sizes,
            "silhouette": recognition.silhouette,
            "debug_report": str(debug_report) if debug_report else None,
            "animation_html": str(animation_path) if animation_path else None,
            "solution": {
                "solved": solution.solved,
                "eliminated": solution.eliminated,
                "target": solution.target,
                "moves": [
                    {
                        "source": move.source,
                        "destination": move.destination,
                        "count": move.count,
                        "completes_branch": move.completes_branch,
                    }
                    for move in solution.moves
                ],
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if animation_path:
            print(f"animation_html={animation_path}")
        print(_format_board(recognition))
        print(_format_solution(solution, args.show_moves))
    return 0 if solution.moves or recognition.state.is_finished else 2


def play(args: argparse.Namespace) -> int:
    if args.moves_per_plan < 1:
        raise ValueError("--moves-per-plan must be positive")
    if args.capture_interval <= 0:
        raise ValueError("--capture-interval must be positive")
    if args.capture_attempts < 2:
        raise ValueError("--capture-attempts must be at least 2")
    if args.tap_gap < 0:
        raise ValueError("--tap-gap must not be negative")
    if args.move_wait < 0:
        raise ValueError("--move-wait must not be negative")
    if args.elimination_wait < 0:
        raise ValueError("--elimination-wait must not be negative")
    if args.interruption_timeout <= 0:
        raise ValueError("--interruption-timeout must be positive")
    if args.interruption_poll_interval <= 0:
        raise ValueError("--interruption-poll-interval must be positive")
    if args.no_move_confirmations < 1:
        raise ValueError("--no-move-confirmations must be positive")

    controller = _controller(args)
    recognizer = _recognizer(args)
    solver = _solver(args)
    run_directory = _create_run_directory()
    print(f"run_debug_dir={run_directory}")
    previous_key: tuple[tuple[int, ...], ...] | None = None
    expected_key: tuple[Branch, ...] | None = None
    expected_summary: tuple[int, int] | None = None
    previous_summary: tuple[int, int] | None = None
    no_move_key: tuple[Branch, ...] | None = None
    no_move_confirmations = 0
    selection_reset_required = True
    unchanged = 0

    try:
        if args.wait_for_start:
            _prepare_manual_start(controller)

        for turn in range(1, args.max_turns + 1):
            turn_name = f"turn-{turn:03d}"
            _screenshot, recognition = _capture_game_board(
                controller,
                recognizer,
                args,
                run_directory,
                turn_name,
                previous_summary,
            )
            current_summary = _recognition_summary(recognition)
            previous_summary = current_summary
            print(f"\nTurn {turn}")
            print(_format_board(recognition))
            if recognition.state.is_finished:
                print("No birds remain: game finished.")
                return 0

            actual_physical_key = _physical_state_key(recognition.state)
            state_mismatch = (
                expected_key is not None and actual_physical_key != expected_key
            ) or (
                expected_summary is not None and current_summary != expected_summary
            )
            if state_mismatch:
                print(
                    "检测到实际棋盘与上一批预期不一致；可能有点击未生效，"
                    "清除残留选择并按当前截图重新规划。"
                )
                previous_key = None
                unchanged = 0
            expected_key = None
            expected_summary = None

            # Reset once at startup and after uncertain device state. Successful
            # batches do not need another neutral tap before every replan.
            if (state_mismatch or selection_reset_required) and not args.dry_run:
                controller.clear_selection(recognition.image_size)
                time.sleep(args.tap_gap)
                selection_reset_required = False

            key = recognition.state.canonical_key()
            unchanged = unchanged + 1 if key == previous_key else 0
            if unchanged >= 2:
                raise RuntimeError(
                    "The board did not change after two tap attempts. Check screen "
                    "scale, device automation permissions, or increase --move-wait."
                )
            previous_key = key

            solution = solver.solve(recognition.state)
            batch = _next_move_batch(solution.moves, args.moves_per_plan)
            print(_format_solution(solution, len(batch)))
            if not solution.moves:
                if actual_physical_key == no_move_key:
                    no_move_confirmations += 1
                else:
                    no_move_key = actual_physical_key
                    no_move_confirmations = 1
                if no_move_confirmations < args.no_move_confirmations:
                    print(
                        "未找到可执行移动，先不退出；将重新截图确认"
                        f"（{no_move_confirmations}/{args.no_move_confirmations}）。"
                    )
                    continue
                print(
                    "连续稳定截图均未找到可执行移动，停止且不进行随机点击。"
                )
                return 2
            no_move_key = None
            no_move_confirmations = 0

            if args.dry_run:
                for number, move in enumerate(batch, 1):
                    print(
                        f"dry-run {number}: #{move.source:02d} -> "
                        f"#{move.destination:02d}"
                    )
                return 0

            virtual_state = recognition.state
            interrupted = False
            for batch_index, move in enumerate(batch):
                # The stable capture after a batch also validates its final
                # state, so only pay for an extra screenshot after each pair
                # of moves inside longer batches.
                if batch_index and batch_index % 2 == 0:
                    quick_screen = controller.capture()
                    if not recognizer.has_game_board(quick_screen):
                        _save_play_screenshot(
                            quick_screen,
                            run_directory,
                            f"{turn_name}-mid-batch-interruption.png",
                            args.save_frames,
                        )
                        print("批量操作中检测到非棋盘画面，暂停当前方案。")
                        selection_reset_required = True
                        interrupted = True
                        break
                    try:
                        observed = recognizer.read(quick_screen)
                    except RecognitionError:
                        observed = None
                    if (
                        observed is None
                        or _physical_state_key(observed.state)
                        != _physical_state_key(virtual_state)
                    ):
                        _save_play_screenshot(
                            quick_screen,
                            run_directory,
                            f"{turn_name}-mid-batch-state-mismatch.png",
                            args.save_frames,
                        )
                        print(
                            "批量操作中检测到实际棋盘与预期不一致，"
                            "停止旧方案并清除残留选择。"
                        )
                        controller.clear_selection(quick_screen.size)
                        time.sleep(args.tap_gap)
                        selection_reset_required = False
                        interrupted = True
                        break

                source = _click_point_for_contents(
                    recognition.branches[move.source],
                    virtual_state.branches[move.source],
                )
                destination = _destination_click_point(
                    recognition.branches[move.destination],
                    source,
                )
                print(
                    f"batch {batch_index + 1}/{len(batch)}: "
                    f"tap {source} -> {destination}"
                )
                controller.tap_pair(source, destination, args.tap_gap)
                virtual_state = virtual_state.apply(move)
                time.sleep(
                    args.elimination_wait if move.completes_branch else args.move_wait
                )

            if interrupted:
                previous_key = None
                unchanged = 0
                expected_key = None
                expected_summary = None
            elif virtual_state.is_finished:
                print("Planned moves eliminated all remaining birds: game finished.")
                return 0
            else:
                eliminated = bool(batch and batch[-1].completes_branch)
                expected_key = None if eliminated else _physical_state_key(virtual_state)
                expected_summary = (
                    (current_summary[0] - 1, current_summary[1] - 4)
                    if eliminated
                    else current_summary
                )

        print(f"Stopped after --max-turns={args.max_turns}.")
        return 2
    finally:
        controller.close()
        if args.debug_reports == "deferred":
            _write_deferred_debug_reports(recognizer, run_directory)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suanniao",
        description="Recognize, solve, and automatically play the bird-branch game.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--types",
        type=int,
        default=None,
        help="number of bird types; default: infer automatically",
    )
    common.add_argument("--max-types", type=int, default=10)
    common.add_argument("--beam-width", type=int, default=2_000)
    common.add_argument("--max-depth", type=int, default=80)
    common.add_argument("--time-limit", type=float, default=20.0)

    commands = parser.add_subparsers(dest="command", required=True)
    analyze_parser = commands.add_parser(
        "analyze", parents=[common], help="recognize and solve one screenshot"
    )
    analyze_parser.add_argument("image", type=Path)
    analyze_parser.add_argument(
        "--show-moves", type=int, default=12, help="number of planned moves to print"
    )
    analyze_parser.add_argument("--json", action="store_true")
    analyze_parser.add_argument(
        "--debug-dir",
        type=Path,
        help=(
            "save branch detection, bird crops, and clustering candidates; "
            "default: <image-stem>-clusters"
        ),
    )
    analyze_parser.add_argument(
        "--html-output",
        type=Path,
        help="solution animation path; default: <image-stem>-solution.html",
    )
    analyze_parser.add_argument(
        "--no-html",
        action="store_true",
        help="do not generate the solution animation HTML",
    )
    analyze_parser.set_defaults(handler=analyze)

    play_parser = commands.add_parser(
        "play",
        parents=[common],
        help="play Android through ADB or iPhone through WebDriverAgent",
    )
    play_parser.add_argument(
        "--platform",
        choices=("android", "ios"),
        default="android",
        help="device automation backend; default: android",
    )
    play_parser.add_argument("--adb", default="adb")
    play_parser.add_argument("--serial")
    play_parser.add_argument(
        "--wda-url",
        default="http://127.0.0.1:8100",
        help="WebDriverAgent URL used with --platform ios",
    )
    play_parser.add_argument(
        "--wda-timeout",
        type=float,
        default=10.0,
        help="WebDriverAgent HTTP timeout in seconds",
    )
    play_parser.add_argument(
        "--wda-session-id",
        help="reuse an existing WebDriverAgent session instead of creating one",
    )
    play_parser.add_argument(
        "--wda-default-active-application",
        default="com.tencent.xin",
        help=(
            "prefer this foreground bundle id for WDA coordinate actions; "
            "default: com.tencent.xin"
        ),
    )
    play_parser.add_argument(
        "--wda-quiescence-timeout",
        type=float,
        default=0.0,
        help=(
            "maximum WDA idle/animation wait after coordinate actions; "
            "default: 0 (disabled)"
        ),
    )
    play_parser.add_argument(
        "--wait-for-start",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "warm the device session and screenshot channel, then wait for Enter "
            "before the first game capture"
        ),
    )
    play_parser.add_argument(
        "--debug-reports",
        choices=("live", "deferred", "off"),
        default="live",
        help=(
            "write cluster reports during play, after play, or not at all; "
            "default: live"
        ),
    )
    play_parser.add_argument("--tap-gap", type=float, default=0.20)
    play_parser.add_argument("--move-wait", type=float, default=0.20)
    play_parser.add_argument(
        "--elimination-wait",
        type=float,
        default=0.55,
        help="wait after a move that eliminates a branch; default: 0.55",
    )
    play_parser.add_argument(
        "--moves-per-plan",
        type=int,
        default=8,
        help="execute this many planned moves before screenshot/replanning; default: 8",
    )
    play_parser.add_argument(
        "--capture-interval",
        type=float,
        default=0.10,
        help="stable screenshot comparison interval; default: 0.10",
    )
    play_parser.add_argument(
        "--capture-attempts",
        type=int,
        default=5,
        help="maximum stable screenshot attempts; default: 5",
    )
    play_parser.add_argument(
        "--interruption-timeout",
        type=float,
        default=300.0,
        help="maximum seconds to wait for the game board after an interruption",
    )
    play_parser.add_argument(
        "--interruption-poll-interval",
        type=float,
        default=0.8,
        help="seconds between interruption recovery checks; default: 0.8",
    )
    play_parser.add_argument(
        "--no-move-confirmations",
        type=int,
        default=2,
        help="stable no-move screenshots required before stopping; default: 2",
    )
    play_parser.add_argument("--max-turns", type=int, default=100)
    play_parser.add_argument("--save-frames")
    play_parser.add_argument("--dry-run", action="store_true")
    play_parser.set_defaults(handler=play, beam_width=120, time_limit=2.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(args.handler(args))
    except (RecognitionError, DeviceError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
