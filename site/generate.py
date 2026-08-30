#!/usr/bin/env python3
"""Generate the static site in docs/ from experiments/*/site-data.json.

No external dependencies (stdlib only). Run from repo root:

    python3 site/generate.py
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = ROOT / "experiments"
DOCS_DIR = ROOT / "docs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def load_experiments():
    experiments = []
    for site_data_path in sorted(EXPERIMENTS_DIR.glob("*/site-data.json")):
        data = json.loads(site_data_path.read_text())
        data["_slug"] = site_data_path.parent.name
        experiments.append(data)
    experiments.sort(key=lambda e: e.get("date", ""), reverse=True)
    return experiments


def esc(value):
    return html.escape(str(value))


def status_badge(status):
    status = status or "complete"
    label = {"in-progress": "In progress", "complete": "Complete"}.get(status, status)
    return f'<span class="badge badge-{esc(status)}">{esc(label)}</span>'


def render_index(experiments):
    template = (TEMPLATES_DIR / "index.html").read_text()
    cards = []
    for exp in experiments:
        best = max(exp["results"], key=lambda r: r["mean"]) if exp.get("results") else None
        headline = (
            f'{esc(best["name"])} leads at {best["mean"]:.3f}' if best else ""
        )
        cards.append(f"""
        <a class="card" href="experiments/{esc(exp['_slug'])}/">
          <div class="card-top">
            <span class="card-category">{esc(exp.get('category', ''))}</span>
            {status_badge(exp.get('status'))}
          </div>
          <h2>{esc(exp['title'])}</h2>
          <p class="card-summary">{esc(exp['summary'])}</p>
          <div class="card-footer">
            <span class="card-headline">{headline}</span>
            <span class="card-date">{esc(exp.get('date', ''))}</span>
          </div>
        </a>""")
    return template.replace("{{CARDS}}", "\n".join(cards)).replace(
        "{{COUNT}}", str(len(experiments))
    )


def render_experiment(exp):
    template = (TEMPLATES_DIR / "experiment.html").read_text()

    rows = []
    max_mean = max((r["mean"] for r in exp["results"]), default=1) or 1
    bars = []
    for r in exp["results"]:
        pct = round(100 * r["mean"] / max_mean, 1)
        ci_low_pct = round(100 * r["ci_low"] / max_mean, 1)
        ci_high_pct = round(100 * r["ci_high"] / max_mean, 1)
        bars.append(f"""
        <div class="bar-row">
          <div class="bar-label">{esc(r['name'])}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{pct}%"></div>
            <div class="bar-ci" style="left:{ci_low_pct}%; width:{max(ci_high_pct - ci_low_pct, 0.5)}%"
                 title="95% CI [{r['ci_low']:.3f}, {r['ci_high']:.3f}]"></div>
          </div>
          <div class="bar-value">{r['mean']:.3f}</div>
        </div>""")
        rows.append(f"""
        <tr>
          <td>{esc(r['name'])}</td>
          <td>{r['mean']:.4f}</td>
          <td>[{r['ci_low']:.4f}, {r['ci_high']:.4f}]</td>
          <td>{r['n']}</td>
        </tr>""")

    notes = "".join(f"<li>{esc(n)}</li>" for n in exp.get("notes", []))
    metric = exp.get("metric", {})

    out = template
    out = out.replace("{{TITLE}}", esc(exp["title"]))
    out = out.replace("{{SUMMARY}}", esc(exp["summary"]))
    out = out.replace("{{STATUS_BADGE}}", status_badge(exp.get("status")))
    out = out.replace("{{DATE}}", esc(exp.get("date", "")))
    out = out.replace("{{CATEGORY}}", esc(exp.get("category", "")))
    out = out.replace("{{TASK_DESCRIPTION}}", esc(exp.get("task_description", "")))
    out = out.replace("{{METRIC_NAME}}", esc(metric.get("name", "")))
    out = out.replace("{{METRIC_DESCRIPTION}}", esc(metric.get("description", "")))
    out = out.replace("{{DATASET_NAME}}", esc(exp.get("dataset", {}).get("name", "")))
    out = out.replace("{{DATASET_URL}}", esc(exp.get("dataset", {}).get("url", "#")))
    out = out.replace("{{DATASET_LICENSE}}", esc(exp.get("dataset", {}).get("license", "")))
    out = out.replace("{{METHODOLOGY_URL}}", esc(exp.get("methodology_url", "#")))
    out = out.replace("{{BARS}}", "\n".join(bars))
    out = out.replace("{{ROWS}}", "\n".join(rows))
    out = out.replace("{{NOTES}}", notes)
    return out


def main():
    experiments = load_experiments()
    DOCS_DIR.mkdir(exist_ok=True)

    style = (TEMPLATES_DIR / "style.css").read_text()
    (DOCS_DIR / "style.css").write_text(style)

    (DOCS_DIR / "index.html").write_text(render_index(experiments))

    for exp in experiments:
        exp_dir = DOCS_DIR / "experiments" / exp["_slug"]
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "index.html").write_text(render_experiment(exp))

    (DOCS_DIR / ".nojekyll").write_text("")
    print(f"Generated site for {len(experiments)} experiment(s) into {DOCS_DIR}")


if __name__ == "__main__":
    main()
