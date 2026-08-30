#!/usr/bin/env python3
"""Generate the static site in docs/ from experiments/*/site-data.json.

No external dependencies (stdlib only). Run from repo root:

    python3 site/generate.py
"""
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = ROOT / "experiments"
DOCS_DIR = ROOT / "docs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_experiments():
    experiments = []
    skipped = []
    for site_data_path in sorted(EXPERIMENTS_DIR.glob("*/site-data.json")):
        data = json.loads(site_data_path.read_text())
        data["_slug"] = site_data_path.parent.name
        if data.get("draft"):
            skipped.append(data["_slug"])
            continue
        experiments.append(data)
    experiments.sort(key=lambda e: e.get("date", ""), reverse=True)
    if skipped:
        print(f"Skipping draft experiment(s) (not published to site): {', '.join(skipped)}")
    return experiments


def esc(value):
    return html.escape(str(value))


def status_badge(status):
    status = status or "complete"
    label = {"in-progress": "In progress", "complete": "Complete"}.get(status, status)
    return f'<span class="badge badge-{esc(status)}">{esc(label)}</span>'


def render_index(experiments):
    template = (TEMPLATES_DIR / "index.html").read_text()
    rows = []
    for i, exp in enumerate(experiments, start=1):
        best = max(exp["results"], key=lambda r: r["mean"]) if exp.get("results") else None
        headline = f'{esc(best["name"])} &middot; {best["mean"]:.3f}' if best else ""
        rows.append(f"""
        <a class="index-row" href="experiments/{esc(exp['_slug'])}/" data-reveal data-reveal-group="index">
          <span class="index-num">{i:02d}</span>
          <div class="index-main">
            <div class="index-top-line">
              <span class="index-category">{esc(exp.get('category', ''))}</span>
              {status_badge(exp.get('status'))}
            </div>
            <h2 class="index-title">{esc(exp['title'])}</h2>
            <p class="index-summary">{esc(exp['summary'])}</p>
          </div>
          <div class="index-side">
            <span class="index-headline">{headline}</span>
            <span class="index-date">{esc(exp.get('date', ''))}</span>
            <span class="index-arrow">&rarr;</span>
          </div>
        </a>""")
    return template.replace("{{CARDS}}", "\n".join(rows)).replace(
        "{{COUNT}}", str(len(experiments))
    )


def render_experiment(exp, index):
    template = (TEMPLATES_DIR / "experiment.html").read_text()

    rows = []
    for r in exp["results"]:
        rows.append(f"""
        <tr>
          <td>{esc(r['name'])}</td>
          <td>{r['mean']:.4f}</td>
          <td>[{r['ci_low']:.4f}, {r['ci_high']:.4f}]</td>
          <td>{r['n']}</td>
        </tr>""")

    notes = "".join(f"<li>{esc(n)}</li>" for n in exp.get("notes", []))
    metric = exp.get("metric", {})

    axis_max = max((r["ci_high"] for r in exp["results"]), default=1)
    metric_range = metric.get("range")
    if metric_range and len(metric_range) == 2:
        axis_max = metric_range[1]
    else:
        axis_max = round(axis_max * 1.15, 2)

    results_json = json.dumps({
        "labels": [r["name"] for r in exp["results"]],
        "means": [r["mean"] for r in exp["results"]],
        "ci_low": [r["ci_low"] for r in exp["results"]],
        "ci_high": [r["ci_high"] for r in exp["results"]],
        "ns": [r["n"] for r in exp["results"]],
        "metricName": metric.get("name", "Score"),
        "axisMax": axis_max,
    })

    out = template
    out = out.replace("{{TITLE}}", esc(exp["title"]))
    out = out.replace("{{SUMMARY}}", esc(exp["summary"]))
    out = out.replace("{{STATUS_BADGE}}", status_badge(exp.get("status")))
    out = out.replace("{{DATE}}", esc(exp.get("date", "")))
    out = out.replace("{{CATEGORY}}", esc(exp.get("category", "")))
    out = out.replace("{{INDEX}}", f"{index:02d}")
    out = out.replace("{{TASK_DESCRIPTION}}", esc(exp.get("task_description", "")))
    out = out.replace("{{METRIC_NAME}}", esc(metric.get("name", "")))
    out = out.replace("{{METRIC_DESCRIPTION}}", esc(metric.get("description", "")))
    out = out.replace("{{DATASET_NAME}}", esc(exp.get("dataset", {}).get("name", "")))
    out = out.replace("{{DATASET_URL}}", esc(exp.get("dataset", {}).get("url", "#")))
    out = out.replace("{{DATASET_LICENSE}}", esc(exp.get("dataset", {}).get("license", "")))
    out = out.replace("{{METHODOLOGY_URL}}", esc(exp.get("methodology_url", "#")))
    out = out.replace("{{ROWS}}", "\n".join(rows))
    out = out.replace("{{NOTES}}", notes)
    out = out.replace("{{RESULTS_JSON}}", results_json)
    return out


def main():
    experiments = load_experiments()
    DOCS_DIR.mkdir(exist_ok=True)

    for asset in ("style.css", "main.js", "chart.js", "theme.js"):
        (DOCS_DIR / asset).write_text((TEMPLATES_DIR / asset).read_text())

    (DOCS_DIR / "index.html").write_text(render_index(experiments))

    published_slugs = set()
    for i, exp in enumerate(experiments, start=1):
        exp_dir = DOCS_DIR / "experiments" / exp["_slug"]
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "index.html").write_text(render_experiment(exp, i))
        published_slugs.add(exp["_slug"])

    # Remove any previously-generated experiment page that's no longer
    # published (draft flipped on, site-data.json deleted, etc.) so stale
    # pages don't linger in docs/.
    docs_experiments_dir = DOCS_DIR / "experiments"
    if docs_experiments_dir.exists():
        for stale_dir in docs_experiments_dir.iterdir():
            if stale_dir.is_dir() and stale_dir.name not in published_slugs:
                shutil.rmtree(stale_dir)
                print(f"Removed stale generated page: docs/experiments/{stale_dir.name}")

    (DOCS_DIR / ".nojekyll").write_text("")
    print(f"Generated site for {len(experiments)} experiment(s) into {DOCS_DIR}")


if __name__ == "__main__":
    main()
