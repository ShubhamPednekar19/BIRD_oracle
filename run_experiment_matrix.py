#!/usr/bin/env python3
"""Run a full hybrid/vector experiment matrix from a YAML config file."""

from __future__ import annotations

import argparse
import itertools
import subprocess
from pathlib import Path
from typing import Any

import json


def _load_config(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Config must be JSON-formatted YAML (YAML 1.2 compatible).") from exc
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping/object.")
    return data


def _validate(config: dict[str, Any]) -> None:
    required = [
        "connection_string",
        "modes",
        "search_types",
        "dataset_forms",
        "common",
        "results_root",
    ]
    missing = [k for k in required if k not in config]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")

    if "hybrid" in config["search_types"] and not config.get("hybrid_scorers"):
        raise ValueError("search_types includes 'hybrid' but 'hybrid_scorers' is empty/missing")

    allowed_modes = {"unified", "parallel"}
    bad_modes = [m for m in config["modes"] if m not in allowed_modes]
    if bad_modes:
        raise ValueError(f"Unsupported modes: {bad_modes}; allowed={sorted(allowed_modes)}")

    allowed_search = {"vector", "hybrid"}
    bad_search = [s for s in config["search_types"] if s not in allowed_search]
    if bad_search:
        raise ValueError(f"Unsupported search_types: {bad_search}; allowed={sorted(allowed_search)}")

    allowed_forms = {"single-user", "multiple"}
    bad_forms = [d for d in config["dataset_forms"] if d not in allowed_forms]
    if bad_forms:
        raise ValueError(f"Unsupported dataset_forms: {bad_forms}; allowed={sorted(allowed_forms)}")


def _experiment_path(results_root: Path, mode: str, search_type: str, scorer: str | None, dataset_form: str) -> Path:
    parts = [results_root, mode, search_type]
    if scorer:
        parts.append(scorer.lower())
    parts.append(dataset_form)
    out = Path(parts[0])
    for p in parts[1:]:
        out = out / p
    return out


def _build_command(config: dict[str, Any], mode: str, search_type: str, scorer: str | None, dataset_form: str, out_dir: Path) -> list[str]:
    common = config.get("common", {})

    cmd = [
        "python",
        "run_hybrid_search_evaluation.py",
        "--connection-string",
        str(config["connection_string"]),
        "--mode",
        mode,
        "--search-type",
        search_type,
        "--discover-k",
        str(common.get("discover_k", 10)),
        "--discover-unified-score-threshold",
        str(common.get("discover_score_threshold", 0.60)),
        "--output",
        str(out_dir / "results.csv"),
        "--summary",
        str(out_dir / "summary.csv"),
        "--html",
        str(out_dir / "report.html"),
    ]

    if dataset_form == "single-user":
        cmd.append("--single-user-mode")

    if search_type == "hybrid" and scorer:
        cmd.extend(["--discover-search-scorer", scorer])
        override = (config.get("scorer_overrides") or {}).get(scorer, {})

        if "discover_vector_rank_penalty" in override:
            cmd.extend(["--discover-vector-rank-penalty", str(override["discover_vector_rank_penalty"])])
        if "discover_text_rank_penalty" in override:
            cmd.extend(["--discover-text-rank-penalty", str(override["discover_text_rank_penalty"])])
        if "discover_vector_score_weight" in override:
            cmd.extend(["--discover-vector-score-weight", str(override["discover_vector_score_weight"])])
        if "discover_text_score_weight" in override:
            cmd.extend(["--discover-text-score-weight", str(override["discover_text_score_weight"])])

    passthrough = config.get("passthrough_args", [])
    if passthrough:
        cmd.extend(str(x) for x in passthrough)

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run experiment matrix from YAML config")
    parser.add_argument("--config", default="experiment_matrix.yaml", help="Path to YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Only print commands without executing")
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _validate(config)

    results_root = Path(config.get("results_root", "results"))
    results_root.mkdir(parents=True, exist_ok=True)

    total = 0
    failures = 0

    for mode, search_type, dataset_form in itertools.product(
        config["modes"], config["search_types"], config["dataset_forms"]
    ):
        scorers = config.get("hybrid_scorers", []) if search_type == "hybrid" else [None]

        for scorer in scorers:
            out_dir = _experiment_path(results_root, mode, search_type, scorer, dataset_form)
            out_dir.mkdir(parents=True, exist_ok=True)

            cmd = _build_command(config, mode, search_type, scorer, dataset_form, out_dir)
            total += 1

            print(f"\n[{total}] mode={mode} search_type={search_type} scorer={scorer or '-'} dataset={dataset_form}")
            print(" ".join(cmd))

            if args.dry_run:
                continue

            completed = subprocess.run(cmd, check=False)
            if completed.returncode != 0:
                failures += 1
                print(f"Experiment failed with exit code {completed.returncode}")

    print(f"\nCompleted {total} experiments. Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
