from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .controller import (
    AdbController,
    DeviceController,
    DeviceError,
    WdaController,
)
from .model import REMOVED, Branch
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
    screenshot,
    run_directory: Path,
    filename: str,
    extra_directory: str | None,
) -> None:
    screenshot.save(run_directory / filename)
    if extra_directory:
        directory = Path(extra_directory)
        directory.mkdir(parents=True, exist_ok=True)
        screenshot.save(directory / filename)


def _capture_game_board(
    controller: DeviceController,
    recognizer: BoardRecognizer,
    args: argparse.Namespace,
    run_directory: Path,
    turn_name: str,
) -> tuple[object, RecognitionResult]:
    deadline = time.monotonic() + args.interruption_timeout
    interruption_index = 0
    waiting = False

    while True:
        screenshot = controller.capture_stable(
            interval=args.capture_interval,
            attempts=args.capture_attempts,
        )
        if recognizer.has_game_board(screenshot):
            _save_play_screenshot(
                screenshot,
                run_directory,
                f"{turn_name}.png",
                args.save_frames,
            )
            recognition = recognizer.read(
                screenshot,
                debug_dir=run_directory / f"{turn_name}-clusters",
            )
            if waiting:
                print("已重新检测到游戏棋盘，继续操作。")
            return screenshot, recognition

        waiting = True
        interruption_index += 1
        _save_play_screenshot(
            screenshot,
            run_directory,
            f"{turn_name}-interruption-{interruption_index:03d}.png",
            args.save_frames,
        )
        dismissed = not args.dry_run and controller.dismiss_interruption()
        if dismissed:
            print("未检测到正常棋盘，找到关闭/跳过按钮，已自动点击。")
        elif interruption_index == 1:
            print(
                "未检测到正常棋盘，也没有找到可用的关闭按钮。"
                "请手动关闭广告窗口，程序会等待棋盘恢复。"
            )

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


def analyze(args: argparse.Namespace) -> int:
    recognition = _recognizer(args).read(args.image, debug_dir=args.debug_dir)
    debug_report = Path(args.debug_dir) / "index.html" if args.debug_dir else None
    if debug_report and not args.json:
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
    if args.interruption_timeout <= 0:
        raise ValueError("--interruption-timeout must be positive")
    if args.interruption_poll_interval <= 0:
        raise ValueError("--interruption-poll-interval must be positive")

    controller = _controller(args)
    recognizer = _recognizer(args)
    solver = _solver(args)
    run_directory = _create_run_directory()
    print(f"run_debug_dir={run_directory}")
    previous_key: tuple[tuple[int, ...], ...] | None = None
    unchanged = 0

    try:
        for turn in range(1, args.max_turns + 1):
            turn_name = f"turn-{turn:03d}"
            _screenshot, recognition = _capture_game_board(
                controller,
                recognizer,
                args,
                run_directory,
                turn_name,
            )
            print(f"\nTurn {turn}")
            print(_format_board(recognition))
            if recognition.state.is_finished:
                print("No birds remain: game finished.")
                return 0

            key = recognition.state.canonical_key()
            unchanged = unchanged + 1 if key == previous_key else 0
            if unchanged >= 2:
                raise RuntimeError(
                    "The board did not change after two tap attempts. Check screen "
                    "scale, device automation permissions, or increase --move-wait."
                )
            previous_key = key

            solution = solver.solve(recognition.state)
            batch = solution.moves[: args.moves_per_plan]
            print(_format_solution(solution, len(batch)))
            if not solution.moves:
                print("No improving move was found; stopping without making a random tap.")
                return 2

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
                if batch_index:
                    quick_screen = controller.capture()
                    if not recognizer.has_game_board(quick_screen):
                        _save_play_screenshot(
                            quick_screen,
                            run_directory,
                            f"{turn_name}-mid-batch-interruption.png",
                            args.save_frames,
                        )
                        print("批量操作中检测到非棋盘画面，暂停当前方案。")
                        interrupted = True
                        break

                source = _click_point_for_contents(
                    recognition.branches[move.source],
                    virtual_state.branches[move.source],
                )
                destination = _click_point_for_contents(
                    recognition.branches[move.destination],
                    virtual_state.branches[move.destination],
                )
                print(
                    f"batch {batch_index + 1}/{len(batch)}: "
                    f"tap {source} -> {destination}"
                )
                controller.tap(*source)
                time.sleep(args.tap_gap)
                controller.tap(*destination)
                virtual_state = virtual_state.apply(move)
                time.sleep(
                    args.elimination_wait if move.completes_branch else args.move_wait
                )

            if interrupted:
                previous_key = None
                unchanged = 0
            elif virtual_state.is_finished:
                print("Planned moves eliminated all remaining birds: game finished.")
                return 0

        print(f"Stopped after --max-turns={args.max_turns}.")
        return 2
    finally:
        controller.close()


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
        help="save branch detection, bird crops, and all clustering candidates",
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
    play_parser.add_argument("--tap-gap", type=float, default=0.08)
    play_parser.add_argument("--move-wait", type=float, default=0.40)
    play_parser.add_argument(
        "--elimination-wait",
        type=float,
        default=0.65,
        help="wait after a move that eliminates a branch; default: 0.65",
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
        default=0.12,
        help="stable screenshot comparison interval; default: 0.12",
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
    play_parser.add_argument("--max-turns", type=int, default=100)
    play_parser.add_argument("--save-frames")
    play_parser.add_argument("--dry-run", action="store_true")
    play_parser.set_defaults(handler=play, beam_width=500, time_limit=8.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(args.handler(args))
    except (RecognitionError, DeviceError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
