#!/usr/bin/env python3
"""Run a full hybrid/vector experiment matrix from a YAML config file."""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from pathlib import Path
from typing import Any


def _load_config(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    # Keep the config dependency-free: allow comment-only lines (starting with '#')
    # and parse the remaining content as JSON-formatted YAML.
    filtered_lines = []
    for line in raw.splitlines():
        if line.lstrip().startswith("#"):
            continue
        filtered_lines.append(line)
    cleaned = "\n".join(filtered_lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Config parse failed. Use JSON-formatted YAML and comment-only lines that start with '#'."
        ) from exc
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


def _expand_scorer_variants(config: dict[str, Any], scorer: str | None) -> list[tuple[str, dict[str, Any]]]:
    if scorer is None:
        return [("base", {})]

    raw_override = (config.get("scorer_overrides") or {}).get(scorer, {})
    if not raw_override:
        return [("base", {})]

    # Option A: explicit list of override sets
    # "RSF": [{"discover_text_score_weight": 2}, {"discover_text_score_weight": 4}]
    if isinstance(raw_override, list):
        variants: list[tuple[str, dict[str, Any]]] = []
        for i, entry in enumerate(raw_override, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"scorer_overrides.{scorer}[{i - 1}] must be an object")
            variants.append((f"set{i}", entry))
        return variants

    if not isinstance(raw_override, dict):
        raise ValueError(f"scorer_overrides.{scorer} must be an object or list of objects")

    # Option B: cartesian expansion of list-valued fields
    # "RSF": {"discover_vector_score_weight": [10], "discover_text_score_weight": [2,4,6]}
    list_keys = [k for k, v in raw_override.items() if isinstance(v, list)]
    if not list_keys:
        return [("base", raw_override)]

    scalar_items = {k: v for k, v in raw_override.items() if not isinstance(v, list)}
    list_values = [raw_override[k] for k in list_keys]

    variants = []
    for idx, combo in enumerate(itertools.product(*list_values), start=1):
        override = dict(scalar_items)
        label_parts = []
        for k, val in zip(list_keys, combo):
            override[k] = val
            label_parts.append(f"{k}-{val}")
        label = f"set{idx}__" + "__".join(label_parts)
        variants.append((label, override))
    return variants


def _build_command(
    config: dict[str, Any],
    mode: str,
    search_type: str,
    scorer: str | None,
    scorer_override: dict[str, Any],
    dataset_form: str,
) -> list[str]:
    common = config.get("common", {})

    cmd = [
        "python",
        "scripts/run_hybrid_search_evaluation.py",
        "--connection-string",
        str(config["connection_string"]),
        "--mode",
        mode,
        "--search-type",
        search_type,
        "--discover-k",
        str(common.get("discover_k", 10)),
        "--discover-score-threshold",
        str(common.get("discover_score_threshold", 0.60))
    ]

    if dataset_form == "single-user":
        cmd.append("--single-user-mode")

    if search_type == "hybrid" and scorer:
        cmd.extend(["--discover-search-scorer", scorer])

        if "discover_vector_rank_penalty" in scorer_override:
            cmd.extend(["--discover-vector-rank-penalty", str(scorer_override["discover_vector_rank_penalty"])])
        if "discover_text_rank_penalty" in scorer_override:
            cmd.extend(["--discover-text-rank-penalty", str(scorer_override["discover_text_rank_penalty"])])
        if "discover_vector_score_weight" in scorer_override:
            cmd.extend(["--discover-vector-score-weight", str(scorer_override["discover_vector_score_weight"])])
        if "discover_text_score_weight" in scorer_override:
            cmd.extend(["--discover-text-score-weight", str(scorer_override["discover_text_score_weight"])])

    passthrough = config.get("passthrough_args", [])
    if passthrough:
        cmd.extend(str(x) for x in passthrough)

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run experiment matrix from YAML config")
    parser.add_argument("--config", default="config/experiment_matrix.yaml", help="Path to YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Only print commands without executing")
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _validate(config)

    total = 0
    failures = 0

    for mode, search_type, dataset_form in itertools.product(
        config["modes"], config["search_types"], config["dataset_forms"]
    ):
        scorers = config.get("hybrid_scorers", []) if search_type == "hybrid" else [None]

        for scorer in scorers:
            scorer_variants = _expand_scorer_variants(config, scorer)
            for variant_label, scorer_override in scorer_variants:
                cmd = _build_command(
                    config, mode, search_type, scorer, scorer_override, dataset_form
                )
                total += 1

                # print(
                #     f"\n[{total}] mode={mode} search_type={search_type} "
                #     f"scorer={scorer or '-'} variant={variant_label} dataset={dataset_form}"
                # )
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
