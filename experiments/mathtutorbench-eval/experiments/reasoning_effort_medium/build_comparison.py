"""One-off analysis script for this experiment: builds comparison.csv and
comparison_chart.png contrasting reasoning_effort=medium (this experiment)
against reasoning_effort=none (the main run), on the identical 50-dialog
subset. Not part of the reusable pipeline - lives in this experiment folder
since it's specific to this comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.common import jsonl_read, load_config

EXPERIMENT_DIR = Path(__file__).resolve().parent
DIALOG_IDS = set(range(51)) - {22}

MODEL_DISPLAY = {}
for cfg in load_config()["models_under_test"].values():
    MODEL_DISPLAY[cfg["id"]] = cfg["display_name"]


def ci95(scores: np.ndarray) -> float:
    n = len(scores)
    if n <= 1:
        return 0.0
    return 1.96 * np.std(scores, ddof=1) / np.sqrt(n)


def main():
    # Baseline: main run's judged.jsonl, filtered to the same 50 dialog IDs, reasoning_effort=none
    main_judged = jsonl_read(REPO_ROOT / "results" / "judged.jsonl")
    baseline_df = pd.DataFrame(
        [r for r in main_judged if r["dialog_id"] in DIALOG_IDS and r["reasoning_effort"] == "none"]
    )

    # Experiment: this folder's generations + judged, reasoning_effort=medium
    exp_gens = jsonl_read(EXPERIMENT_DIR / "results" / "generations.jsonl")
    exp_judged = jsonl_read(EXPERIMENT_DIR / "results" / "judged.jsonl")
    empty_dialog_keys = {
        (g["model"], g["dialog_id"]) for g in exp_gens if not g["response_text"].strip()
    }
    exp_df = pd.DataFrame(exp_judged)
    exp_df["is_empty"] = exp_df.apply(lambda r: (r["model"], r["dialog_id"]) in empty_dialog_keys, axis=1)

    rows = []
    for model in sorted(set(baseline_df["model"]) | set(exp_df["model"])):
        # none baseline
        b = baseline_df[(baseline_df["model"] == model) & baseline_df["judge_score"].notna()]
        scores = b["judge_score"].to_numpy(dtype=float)
        rows.append({
            "model": model, "condition": "none_baseline", "n": len(scores),
            "mean": float(np.mean(scores)) if len(scores) else float("nan"),
            "ci95": ci95(scores), "empty_response_count": 0,
        })

        # medium, all responses (including empty ones scored by the judge as-is)
        m_all = exp_df[(exp_df["model"] == model) & exp_df["judge_score"].notna()]
        scores = m_all["judge_score"].to_numpy(dtype=float)
        n_empty = int(exp_df[(exp_df["model"] == model)]["is_empty"].sum())
        rows.append({
            "model": model, "condition": "medium_all", "n": len(scores),
            "mean": float(np.mean(scores)) if len(scores) else float("nan"),
            "ci95": ci95(scores), "empty_response_count": n_empty,
        })

        # medium, excluding empty-response rows (isolates reasoning effect from the token-budget confound)
        m_nonempty = m_all[~m_all["is_empty"]]
        scores = m_nonempty["judge_score"].to_numpy(dtype=float)
        rows.append({
            "model": model, "condition": "medium_nonempty_only", "n": len(scores),
            "mean": float(np.mean(scores)) if len(scores) else float("nan"),
            "ci95": ci95(scores), "empty_response_count": n_empty,
        })

    comparison = pd.DataFrame(rows)
    comparison.to_csv(EXPERIMENT_DIR / "results" / "comparison.csv", index=False)
    print(comparison.to_string(index=False))

    # Grouped bar chart
    models = sorted(comparison["model"].unique())
    conditions = ["none_baseline", "medium_all", "medium_nonempty_only"]
    colors = {"none_baseline": "#4C72B0", "medium_all": "#DD8452", "medium_nonempty_only": "#55A868"}
    labels = {"none_baseline": "none (baseline)", "medium_all": "medium (all responses)", "medium_nonempty_only": "medium (non-empty only)"}

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(models))
    width = 0.25
    for i, cond in enumerate(conditions):
        means, errs = [], []
        for model in models:
            row = comparison[(comparison["model"] == model) & (comparison["condition"] == cond)]
            means.append(row["mean"].values[0] if len(row) else 0)
            errs.append(row["ci95"].values[0] if len(row) else 0)
        ax.bar(x + (i - 1) * width, means, width, yerr=errs, capsize=3, label=labels[cond], color=colors[cond])

    ax.axhline(0.50, color="gray", linestyle="--", linewidth=1, label="Judged equal to human (0.50)")
    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_DISPLAY.get(m, m) for m in models])
    ax.set_ylabel("Judge score (0-1), mean +/- 95% CI")
    ax.set_title("Hard-scaffolding (n=50 identical dialogs): reasoning_effort none vs medium")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(EXPERIMENT_DIR / "results" / "comparison_chart.png", dpi=150)
    print(f"\nWrote {EXPERIMENT_DIR / 'results' / 'comparison_chart.png'}")


if __name__ == "__main__":
    main()
