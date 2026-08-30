"""Compute mean + 95% CI per model (per reasoning-effort setting) from
results/judged.jsonl, write results/summary.csv, and render a Braintrust-style
horizontal-band chart to results/summary_chart.png.

CI formula: mean +/- 1.96 * stddev / sqrt(n) (normal approximation to the
95% CI of the mean), computed over all judge scores (dialogs x trials) for
that model/reasoning-effort combination. This is a large-sample approximation,
not a t-distribution interval - noted here since n may be small in early
(--limit-scoped) runs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.common import jsonl_read, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def compute_summary(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["judge_score"].notna()].copy()
    rows = []
    for (model, effort), group in df.groupby(["model", "reasoning_effort"]):
        scores = group["judge_score"].to_numpy(dtype=float)
        n = len(scores)
        mean = float(np.mean(scores))
        std = float(np.std(scores, ddof=1)) if n > 1 else 0.0
        ci95 = 1.96 * std / np.sqrt(n) if n > 1 else 0.0
        rows.append(
            {
                "model": model,
                "reasoning_effort": effort,
                "n": n,
                "mean": mean,
                "std": std,
                "ci95": ci95,
                "ci_low": mean - ci95,
                "ci_high": mean + ci95,
            }
        )
    return pd.DataFrame(rows).sort_values("mean", ascending=False).reset_index(drop=True)


def render_chart(summary: pd.DataFrame, config: dict, chart_path: Path, title: str) -> None:
    display_names = {}
    for cfg in config["models_under_test"].values():
        display_names[cfg["id"]] = cfg["display_name"]

    fig, ax = plt.subplots(figsize=(8, 0.9 * len(summary) + 1.5))
    y_positions = np.arange(len(summary))[::-1]

    for y, (_, row) in zip(y_positions, summary.iterrows()):
        label = display_names.get(row["model"], row["model"])
        ax.barh(y, row["mean"], xerr=row["ci95"], height=0.5, color="#4C72B0",
                ecolor="black", capsize=4)
        ax.text(row["mean"] + row["ci95"] + 0.01, y, f"{row['mean']:.3f}", va="center", fontsize=10)

    ax.axvline(0.50, color="gray", linestyle="--", linewidth=1, label="Judged equal to human (0.50)")
    ax.set_yticks(y_positions)
    ax.set_yticklabels([display_names.get(m, m) for m in summary["model"]])
    ax.set_xlabel("Judge score (0-1), mean +/- 95% CI")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(chart_path, dpi=150)
    print(f"Wrote chart to {chart_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None, help="Override input path (default: results/judged.jsonl)")
    parser.add_argument("--output-csv", type=str, default=None, help="Override summary CSV path")
    parser.add_argument("--output-chart", type=str, default=None, help="Override chart PNG path")
    parser.add_argument("--title", type=str, default="MathTutorBench hard-scaffolding: teacher-turn judge scores")
    args = parser.parse_args()

    judged_path = Path(args.input) if args.input else REPO_ROOT / "results" / "judged.jsonl"
    summary_csv_path = Path(args.output_csv) if args.output_csv else judged_path.parent / "summary.csv"
    chart_path = Path(args.output_chart) if args.output_chart else judged_path.parent / "summary_chart.png"

    rows = jsonl_read(judged_path)
    if not rows:
        raise RuntimeError(f"No judged data found at {judged_path}. Run scripts/run_judge.py first.")

    df = pd.DataFrame(rows)
    n_parse_errors = df["judge_score"].isna().sum()
    if n_parse_errors:
        print(f"WARNING: {n_parse_errors} rows had unparseable judge output and are excluded from stats.")

    summary = compute_summary(df)
    summary.to_csv(summary_csv_path, index=False)
    print(f"Wrote {summary_csv_path}")
    print(summary.to_string(index=False))

    config = load_config()
    render_chart(summary, config, chart_path, args.title)


if __name__ == "__main__":
    main()
