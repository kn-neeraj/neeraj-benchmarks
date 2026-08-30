"""Generate teacher turns from the models under test.

Runs: selected models x selected dialogs x n_trials, at the single
reasoning_effort condition confirmed in config/models.yaml ("none" - see
that file for why the two-condition high/none design was collapsed to one).

Writes raw generations to results/generations.jsonl, one row per
(model, dialog_id, trial). Resumable: rows already present for a given
(model, dialog_id, trial) combo are skipped on re-run.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harbor.task import Instruction, generate_teacher_turn
from scripts.common import OpenCodeGoClient, UsageTracker, jsonl_append, jsonl_read, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPO_ROOT / "data" / "hard_scaffolding.jsonl"


def load_dialogs(limit: int = None, dialog_ids: List[int] = None) -> List[Dict[str, Any]]:
    rows = jsonl_read(DATASET_PATH)
    if not rows:
        raise RuntimeError(
            f"No dataset found at {DATASET_PATH}. Run `python data/fetch_dataset.py` first."
        )
    if dialog_ids is not None:
        wanted = set(dialog_ids)
        rows = [r for r in rows if r["dialog_id"] in wanted]
    elif limit is not None:
        rows = rows[:limit]
    return rows


def completed_keys(path: Path) -> Set[Tuple[str, int, int]]:
    done = set()
    for row in jsonl_read(path):
        done.add((row["model"], row["dialog_id"], row["trial"]))
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models", nargs="+", default=None,
        help="Model keys from config/models.yaml models_under_test (default: all three). "
             "e.g. --models kimi_k3",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of dialogs (default: 5, dry-run scope)")
    parser.add_argument("--trials", type=int, default=1, help="Trials per dialog (default: 1, dry-run scope)")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --limit 5 --trials 1 (the defaults)")
    parser.add_argument("--max-requests", type=int, default=None, help="Safety cap on total generation requests this run")
    parser.add_argument("--max-tokens", type=int, default=200, help="max_tokens per generation call")
    parser.add_argument(
        "--dialog-ids", type=str, default=None,
        help="Comma-separated dialog_id list to run instead of the first --limit dialogs "
             "(for side experiments that need to reuse an exact dialog set across runs)",
    )
    parser.add_argument(
        "--reasoning-effort", type=str, default=None,
        help="Override config/models.yaml's reasoning_effort for this run (e.g. 'medium'). "
             "Used for side experiments; the main run relies on the config default.",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Override the output path (default: results/generations.jsonl). "
             "Used to keep side-experiment output separate from the main run's data.",
    )
    args = parser.parse_args()

    config = load_config()
    all_models = config["models_under_test"]
    reasoning_effort = args.reasoning_effort or config["reasoning_effort"]
    output_path = Path(args.output) if args.output else REPO_ROOT / "results" / "generations.jsonl"

    if args.models:
        selected = {k: all_models[k] for k in args.models}
    else:
        selected = all_models

    dialog_ids = [int(x) for x in args.dialog_ids.split(",")] if args.dialog_ids else None
    dialogs = load_dialogs(limit=args.limit, dialog_ids=dialog_ids)
    done = completed_keys(output_path)

    usage = UsageTracker(max_requests=args.max_requests)
    client = OpenCodeGoClient(config, usage=usage)

    total_planned = len(selected) * len(dialogs) * args.trials
    total_skipped = 0
    total_run = 0

    print(
        f"Plan: {len(selected)} model(s) x {len(dialogs)} dialog(s) x {args.trials} trial(s) "
        f"= {total_planned} generations, reasoning_effort={reasoning_effort!r}"
    )

    for model_key, model_cfg in selected.items():
        model_id = model_cfg["id"]
        for row in dialogs:
            instruction = Instruction.from_row(row)
            for trial in range(args.trials):
                key = (model_id, instruction.dialog_id, trial)
                if key in done:
                    total_skipped += 1
                    continue
                try:
                    result = generate_teacher_turn(
                        client=client,
                        model=model_id,
                        instruction=instruction,
                        reasoning_effort=reasoning_effort,
                        max_tokens=args.max_tokens,
                    )
                except Exception as e:
                    print(f"[ERROR] model={model_id} dialog={instruction.dialog_id} trial={trial}: {e}", file=sys.stderr)
                    continue

                jsonl_append(
                    output_path,
                    {
                        "model": model_id,
                        "model_key": model_key,
                        "dialog_id": instruction.dialog_id,
                        "trial": trial,
                        "reasoning_effort": reasoning_effort,
                        "response_text": result["content"],
                        "finish_reason": result["finish_reason"],
                        "latency_ms": result["latency_ms"],
                        "usage": result["usage"],
                        "ground_truth_response": instruction.ground_truth_response,
                        "question": instruction.question,
                        "reference_solution": instruction.reference_solution,
                        "dialog_history": instruction.dialog_history,
                    },
                )
                total_run += 1
                print(f"  [{total_run}/{total_planned - total_skipped}] {model_id} dialog={instruction.dialog_id} trial={trial} -> {result['content'][:80]!r}")

    print(f"\nDone. Ran {total_run}, skipped {total_skipped} already-completed. Usage: {usage.summary()}")


if __name__ == "__main__":
    main()
