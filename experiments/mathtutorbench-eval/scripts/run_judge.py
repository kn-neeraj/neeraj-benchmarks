"""Score every generation in results/generations.jsonl with the judge model.

Writes results/judged.jsonl (one row per generation, carrying judge_score and
judge_rationale). Resumable: rows already judged for a given
(model, dialog_id, trial) are skipped on re-run. Logs the exact judge prompt
template used to results/judge_prompt.txt on every run, since judge-prompt
sensitivity is a known limitation worth documenting rather than hiding.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harbor.task import Instruction, JUDGE_PROMPT_TEMPLATE, Verifier
from scripts.common import OpenCodeGoClient, UsageTracker, jsonl_append, jsonl_read, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def judged_keys(path: Path) -> Set[Tuple[str, int, int]]:
    done = set()
    for row in jsonl_read(path):
        done.add((row["model"], row["dialog_id"], row["trial"]))
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-requests", type=int, default=None, help="Safety cap on total judge requests this run")
    parser.add_argument("--limit", type=int, default=None, help="Only judge the first N ungraded generations")
    parser.add_argument("--generations", type=str, default=None, help="Override input path (default: results/generations.jsonl)")
    parser.add_argument("--output", type=str, default=None, help="Override output path (default: results/judged.jsonl)")
    args = parser.parse_args()

    config = load_config()
    judge_model = config["judge"]["id"]

    generations_path = Path(args.generations) if args.generations else REPO_ROOT / "results" / "generations.jsonl"
    judged_path = Path(args.output) if args.output else REPO_ROOT / "results" / "judged.jsonl"
    judge_prompt_log_path = judged_path.parent / "judge_prompt.txt"

    judge_prompt_log_path.parent.mkdir(parents=True, exist_ok=True)
    judge_prompt_log_path.write_text(
        f"Judge model: {judge_model}\nTemperature: 0\n\nPrompt template (formatted per-example with "
        f"question/reference_solution/dialog_history/ground_truth_response/candidate_response):\n\n"
        + JUDGE_PROMPT_TEMPLATE
    )

    generations = jsonl_read(generations_path)
    if not generations:
        raise RuntimeError(f"No generations found at {generations_path}. Run scripts/run_generation.py first.")

    done = judged_keys(judged_path)
    to_judge = [
        g for g in generations
        if (g["model"], g["dialog_id"], g["trial"]) not in done
    ]
    n_already_judged = len(generations) - len(to_judge)
    if args.limit is not None:
        to_judge = to_judge[: args.limit]

    usage = UsageTracker(max_requests=args.max_requests)
    client = OpenCodeGoClient(config, usage=usage)
    verifier = Verifier(judge_client=client, judge_model=judge_model)

    print(f"Judging {len(to_judge)} generations ({n_already_judged} already judged) with {judge_model}")

    scored = 0
    for g in to_judge:
        instruction = Instruction(
            dialog_id=g["dialog_id"],
            question=g["question"],
            dialog_history=g["dialog_history"],
            reference_solution=g["reference_solution"],
            ground_truth_response=g["ground_truth_response"],
        )
        try:
            verdict = verifier.score(instruction, g["response_text"])
        except Exception as e:
            print(f"[ERROR] judging model={g['model']} dialog={g['dialog_id']} trial={g['trial']}: {e}", file=sys.stderr)
            continue

        jsonl_append(
            judged_path,
            {
                "model": g["model"],
                "model_key": g["model_key"],
                "dialog_id": g["dialog_id"],
                "trial": g["trial"],
                "reasoning_effort": g["reasoning_effort"],
                "response_text": g["response_text"],
                **verdict,
            },
        )
        scored += 1
        score_str = f"{verdict['judge_score']:.2f}" if verdict["judge_score"] is not None else "PARSE_ERROR"
        print(f"  [{scored}/{len(to_judge)}] {g['model']} dialog={g['dialog_id']} trial={g['trial']} -> score={score_str}")

    print(f"\nDone. Scored {scored}. Usage: {usage.summary()}")


if __name__ == "__main__":
    main()
