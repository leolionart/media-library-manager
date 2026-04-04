from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import load_config
from .models import LibraryTargets, RootConfig
from .operations import apply_plan, load_plan
from .planner import load_report, plan_actions, save_plan
from .scanner import scan_roots
from .web import run_dashboard


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="media-library-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan roots and produce a duplicate report.")
    add_shared_root_arguments(scan_parser)
    scan_parser.add_argument("--output", required=True, help="Path to write the JSON report.")
    scan_parser.set_defaults(func=run_scan)

    plan_parser = subparsers.add_parser("plan", help="Build a move/delete/review plan.")
    add_shared_root_arguments(plan_parser)
    plan_parser.add_argument("--report", help="Existing scan report JSON.")
    plan_parser.add_argument("--output", required=True, help="Path to write the plan JSON.")
    plan_parser.add_argument("--movie-root", help="Canonical root for movies.")
    plan_parser.add_argument("--series-root", help="Canonical root for series.")
    plan_parser.add_argument("--review-root", help="Optional root for items that need review.")
    plan_parser.add_argument("--delete-lower-quality", action="store_true", help="Delete lower-quality same-title items instead of marking them for review.")
    plan_parser.set_defaults(func=run_plan)

    apply_parser = subparsers.add_parser("apply", help="Apply a plan in dry-run or execute mode.")
    apply_parser.add_argument("--plan", required=True, help="Plan JSON produced by the plan command.")
    apply_parser.add_argument("--execute", action="store_true", help="Actually move/delete files. Without this flag the command is dry-run.")
    apply_parser.add_argument("--prune-empty-dirs", action="store_true", help="Remove empty parent directories after move/delete.")
    apply_parser.set_defaults(func=run_apply)

    serve_parser = subparsers.add_parser("serve", help="Run a local dashboard for managing roots and scans.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    serve_parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    serve_parser.add_argument("--state-file", default="./data/app-state.json", help="State file used by the dashboard.")
    serve_parser.set_defaults(func=run_serve)
    return parser


def add_shared_root_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Optional TOML config with roots and targets.")
    parser.add_argument("--root", action="append", default=[], help="Root folder to scan. Can be passed multiple times.")
    parser.add_argument(
        "--priority-root",
        action="append",
        default=[],
        metavar="PRIORITY:PATH",
        help="Root with explicit priority, for example 100:/libraries/media/movies.",
    )


def run_scan(args: argparse.Namespace) -> None:
    roots, _ = resolve_roots_and_targets(args)
    report = scan_roots(roots)
    output_path = Path(args.output)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print_summary("scan", report.to_dict()["summary"], extra={"output": str(output_path)})


def run_plan(args: argparse.Namespace) -> None:
    roots, config_targets = resolve_roots_and_targets(args)
    targets = merge_targets(
        config_targets,
        LibraryTargets(
            movie_root=Path(args.movie_root).expanduser().resolve() if args.movie_root else None,
            series_root=Path(args.series_root).expanduser().resolve() if args.series_root else None,
            review_root=Path(args.review_root).expanduser().resolve() if args.review_root else None,
        ),
    )

    report = load_report(args.report) if args.report else scan_roots(roots)
    plan = plan_actions(report, targets, delete_lower_quality=args.delete_lower_quality)
    save_plan(plan, args.output)
    print_summary("plan", plan["summary"], extra={"output": str(Path(args.output).resolve())})


def run_apply(args: argparse.Namespace) -> None:
    plan = load_plan(args.plan)
    result = apply_plan(plan, execute=args.execute, prune_empty_dirs=args.prune_empty_dirs)
    print_summary("apply", result["summary"], extra={"mode": "execute" if args.execute else "dry-run"})


def run_serve(args: argparse.Namespace) -> None:
    run_dashboard(host=args.host, port=args.port, state_file=Path(args.state_file).expanduser().resolve())


def resolve_roots_and_targets(args: argparse.Namespace) -> tuple[list[RootConfig], LibraryTargets]:
    config_roots: list[RootConfig] = []
    config_targets = LibraryTargets()
    if getattr(args, "config", None):
        config_roots, config_targets = load_config(args.config)

    cli_roots = [RootConfig(path=Path(path).expanduser().resolve(), label=Path(path).name) for path in args.root]
    for entry in args.priority_root:
        priority_text, path_text = entry.split(":", 1)
        path = Path(path_text).expanduser().resolve()
        cli_roots.append(RootConfig(path=path, label=path.name, priority=int(priority_text)))

    roots = cli_roots or config_roots
    if not roots:
        raise SystemExit("No scan roots provided. Use --root, --priority-root, or --config.")
    return roots, config_targets


def merge_targets(base: LibraryTargets, override: LibraryTargets) -> LibraryTargets:
    return LibraryTargets(
        movie_root=override.movie_root or base.movie_root,
        series_root=override.series_root or base.series_root,
        review_root=override.review_root or base.review_root,
    )


def print_summary(command: str, summary: dict[str, Any], *, extra: dict[str, str] | None = None) -> None:
    print(f"{command} summary")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    if extra:
        for key, value in extra.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
