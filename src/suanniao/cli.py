from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .controller import (
    AdbController,
    DeviceController,
    DeviceError,
    WdaController,
)
from .solution_html import write_solution_animation
from .solver import BeamSolver, SolveResult
from .vision import BoardRecognizer, RecognitionError, RecognitionResult


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
    controller = _controller(args)
    recognizer = _recognizer(args)
    solver = _solver(args)
    previous_key: tuple[tuple[int, ...], ...] | None = None
    unchanged = 0

    try:
        for turn in range(1, args.max_turns + 1):
            screenshot = controller.capture_stable()
            if args.save_frames:
                directory = Path(args.save_frames)
                directory.mkdir(parents=True, exist_ok=True)
                screenshot.save(directory / f"turn-{turn:03d}.png")

            recognition = recognizer.read(screenshot)
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
            print(_format_solution(solution, 1))
            if not solution.moves:
                print("No improving move was found; stopping without making a random tap.")
                return 2

            move = solution.moves[0]
            source = recognition.branches[move.source].click_point()
            destination = recognition.branches[move.destination].click_point()
            print(f"tap {source} -> {destination}")
            if args.dry_run:
                return 0
            controller.tap(*source)
            time.sleep(args.tap_gap)
            controller.tap(*destination)
            time.sleep(args.move_wait)

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
    play_parser.add_argument("--tap-gap", type=float, default=0.15)
    play_parser.add_argument("--move-wait", type=float, default=0.8)
    play_parser.add_argument("--max-turns", type=int, default=100)
    play_parser.add_argument("--save-frames")
    play_parser.add_argument("--dry-run", action="store_true")
    play_parser.set_defaults(handler=play)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(args.handler(args))
    except (RecognitionError, DeviceError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
