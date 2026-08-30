# Side experiment: does reasoning effort change scaffolding quality?

## Question

The main replication (see the top-level [README.md](../../README.md)) runs
all three models under test with `reasoning_effort="none"`, matching the
MathTutorBench paper's own convention of evaluating with thinking disabled.
This experiment asks: **does giving the models room to reason before
answering change how well they scaffold**, for better or worse?

Two plausible effects pull in opposite directions:
- More reasoning could let a model better diagnose the student's specific
  error before responding, producing a sharper, more targeted hint.
- More reasoning could cause a model to "solve" the problem internally and
  then leak that solved state into the response, defeating the task's
  actual goal (guide, don't reveal).

## Setup

- **Same 50 dialogs across all 3 models**, so the comparison is paired and
  apples-to-apples. Dialog IDs: 0-50 (51 consecutive IDs) **excluding ID 22**,
  which fails the judge's upstream content-moderation check for all models
  (see the main README/run notes) - so effectively 50 usable IDs.
- **1 trial per dialog** (matching the main run's trial count, itself a
  budget-driven deviation from the original 3-trial design - see the main
  README).
- **reasoning_effort="medium" for all 3 models under test**, kept identical
  across models specifically so any score difference reflects the models'
  actual response to more reasoning budget, not an uncontrolled variable.
- **Judge stays exactly as in the main run**: `qwen3.8-max`, temperature 0,
  `reasoning_effort="none"`, identical prompt template (logged again to
  `results/judge_prompt.txt` in this folder - should be byte-identical to
  the main run's, confirming the only changed variable is the test models'
  reasoning effort).
- **Baseline for comparison**: the same 50 dialog IDs' results already exist
  in the main run's `../../results/judged.jsonl` at `reasoning_effort="none"`.
  This experiment does not re-run the baseline - it filters the existing
  main-run data down to the same 50 IDs for a fair side-by-side.

## Folder contents

```
README.md                   this file
results/generations.jsonl   50 dialogs x 3 models, reasoning_effort=medium
results/judged.jsonl        judge scores for the above
results/judge_prompt.txt    exact judge prompt used (should match the main run's)
results/summary.csv         mean + 95% CI per model, medium condition
results/summary_chart.png   chart, medium condition
results/comparison.csv      medium vs. none, same 50 dialogs, side by side
results/comparison_chart.png
```

## How this was run

Reused the main pipeline's scripts with override flags added for this
purpose (`--dialog-ids`, `--reasoning-effort`, `--output` on
`run_generation.py`; `--generations`/`--output` on `run_judge.py`;
`--input`/`--output-csv`/`--output-chart` on `aggregate_stats.py`) rather
than duplicating pipeline code:

```bash
cd ../..   # repo root
source .venv/bin/activate

python3 scripts/run_generation.py \
  --models kimi_k3 deepseek_v4_flash glm_5_2 \
  --dialog-ids 0,1,2,...,50  \
  --trials 1 \
  --reasoning-effort medium \
  --output experiments/reasoning_effort_medium/results/generations.jsonl \
  --max-requests 200

python3 scripts/run_judge.py \
  --generations experiments/reasoning_effort_medium/results/generations.jsonl \
  --output experiments/reasoning_effort_medium/results/judged.jsonl \
  --max-requests 200

python3 scripts/aggregate_stats.py \
  --input experiments/reasoning_effort_medium/results/judged.jsonl \
  --output-csv experiments/reasoning_effort_medium/results/summary.csv \
  --output-chart experiments/reasoning_effort_medium/results/summary_chart.png \
  --title "Hard-scaffolding (n=50): reasoning_effort=medium"
```

## Caveats

- n=50 per model, much smaller than the main run's n=322 - CIs here will be
  visibly wider. This is a directional side-check, not a claim on par with
  the main result.
- `medium` reasoning effort is not officially documented for these models on
  this endpoint - only confirmed live (see the main README's discovery
  notes for `high`/`none`); confirmed working with a live test call before
  this experiment ran, but its actual reasoning depth/cost per model is
  whatever the provider implements behind that label, not something this
  project controls or can fully characterize.
- Different generations (medium) are judged by the same judge configuration
  as the main run's `none` condition, so any observed difference reflects
  the test models' behavior change, not a judge change - but it is still one
  judge's opinion, same limitation as the main run.

## Results

**Headline finding: this experiment cannot answer the original question
("does reasoning help or hurt scaffolding?") as run, because of a token-budget
bug, not a reasoning-quality effect.** Reporting the numbers below in full,
but do not read them as "medium reasoning is worse at tutoring" - they
mostly measure "what breaks when you enable reasoning without raising the
token budget."

### What went wrong

`run_generation.py`'s default `max_tokens=200` was carried over unchanged
from the main run's `reasoning_effort="none"` condition, where none of that
budget goes to hidden reasoning. Under `reasoning_effort="medium"`, reasoning
tokens draw from the *same* budget as the visible answer:

| Model | Empty responses (of 50) | Failure mode |
|---|---|---|
| DeepSeek V4 Flash | 35 (70%) | `finish_reason="stop"` with nothing - model ends the turn with zero visible content |
| GLM-5.2 | 21 (42%) | `finish_reason="length"` - reasoning alone consumed the full 200-token budget |
| Kimi K3 | 2 (4%) | mostly produced *some* text, but a live diagnostic call (below) shows why even those are unreliable |

A live test call to `kimi-k3` at `reasoning_effort="medium"` with the
production prompt, `max_tokens=200`, reproduced the failure directly:
`content` came back `None` (`finish_reason="length"`) - all 200 tokens went
to the hidden `reasoning` field. Raising `max_tokens` to 600 on the same
prompt produced a clean two-sentence, on-task hint (140 reasoning tokens +
53 answer tokens = 193 total, just over the old budget). This confirms the
budget, not the model's tutoring judgment, is what's failing.

Consistent with this, `kimi-k3`'s 48 nominally "non-empty" responses under
`medium` are dominated by truncated reasoning leaking into the answer field -
e.g. `"Let me analyze the student's work."` or a response that trails off
mid-calculation (`"...220 + 23 = 243, minus 80 = 143. But the student said x
= "`). These are not lower-quality *tutoring* - they're cut-off internal
monologue that never reached the actual answer.

### Numbers (see `results/comparison.csv` and `results/comparison_chart.png`)

| Model | none (baseline, n=50) | medium, all responses (n=50) | medium, non-empty only |
|---|---|---|---|
| GLM-5.2 | 0.755 ± 0.079 | 0.283 ± 0.105 (21 empty) | 0.276 ± 0.131 (n=29) |
| Kimi K3 | 0.642 ± 0.097 | 0.177 ± 0.070 (2 empty) | 0.146 ± 0.058 (n=48) |
| DeepSeek V4 Flash | 0.577 ± 0.093 | 0.513 ± 0.116 (35 empty) | 0.760 ± 0.132 (n=15) |

Note that excluding empty responses does **not** recover a clean signal for
GLM-5.2 or Kimi K3 - their non-empty scores stay just as low, confirming the
"non-empty" responses are still budget-truncated garbage, not genuine
answers. DeepSeek's non-empty subset (n=15, a small and likely biased sample
of "problems where less reasoning was needed") is too small and too
selection-biased to read as "medium reasoning helps DeepSeek."

### Conclusion

No usable conclusion about reasoning effort's effect on pedagogical
scaffolding can be drawn from this run. The real, valid finding is
operational: **naively turning on `reasoning_effort` without re-tuning
`max_tokens` silently corrupts most of the output**, and the failure modes
differ by model (silent-empty vs. token-exhausted vs. truncated-leak) in a
way that would be easy to miss if you only checked score means without
inspecting raw responses, as this writeup did. A valid version of this
experiment would need `max_tokens` raised to comfortably cover
reasoning + answer (the diagnostic call suggests 600+ is enough for
`kimi-k3` at `medium`) before a meaningful medium-vs-none comparison is
possible - not run yet, pending direction.
