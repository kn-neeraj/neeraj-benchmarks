# MathTutorBench hard-scaffolding replication

A replication attempt of the Braintrust eval comparing three open-weight
models on the MathTutorBench "hard scaffolding" task:
https://www.braintrust.dev/evals/kimi-k3-deepseek-v4

Each item is a math problem plus a partial student/teacher dialog. The model
under test writes the next teacher turn (max 2 sentences) without giving away
the answer. An LLM judge scores that turn from 0 to 1 against the real human
teacher's response, where 0.50 means "judged equal to the human."

**Status: scaffolding stage.** Model/judge discovery is complete and
confirmed live (see below). Dataset fetch, generation, judging, and
aggregation scripts are not yet implemented.

## Why this won't match Braintrust's numbers exactly

Braintrust's original eval reports 0.680 / 0.653 / 0.589 for the three
models. Their exact judge model, exact judge prompt, and exact
reasoning-effort parameterization are not public. This replication uses a
different judge model (chosen explicitly to avoid self-preference bias — see
below) and a judge prompt we wrote ourselves and log verbatim to
`results/judge_prompt.txt` on every run.

**What's worth comparing: rank order and confidence-interval overlap across
the three models, not absolute score values.** Treat any exact-value match to
Braintrust's numbers as coincidental, not as validation.

## Model access

Every model call in this project — both the three models under test and the
judge — comes from a single OpenCode Go subscription
(`https://opencode.ai/zen/go/v1`, OpenAI-compatible, `Bearer
$OPENCODE_GO_API_KEY`). This means all quota (the plan's $12/5h, $30/week,
$60/month caps) is shared across every call type; see the cost-tracking
guardrails in `scripts/run_generation.py` / `run_judge.py` once implemented.

### Confirmed model IDs (live-tested 2026-08-29)

Full config: [`config/models.yaml`](config/models.yaml).

| Role | Model | Confirmed API ID |
|---|---|---|
| Model under test | Kimi K3 | `kimi-k3` |
| Model under test | DeepSeek V4 Flash | `deepseek-v4-flash` |
| Model under test | GLM-5.2 | `glm-5.2` |
| **Judge** | **Qwen3.8-Max** | `qwen3.8-max` |

GLM-5.2 is available directly on the Go plan — the GLM-5.3-Flash fallback
considered in planning was not needed.

Two important discovery notes, since the endpoint's ID format doesn't match
the OpenCode TUI config convention:

- The models list lives at `GET /models`, not `/v1/models` (the latter
  404s) — full base is `https://opencode.ai/zen/go/v1/models`.
- IDs are bare strings (`kimi-k3`), not prefixed with `opencode-go/`.

### Judge selection

The judge must not be one of the three models under test, to avoid
self-preference bias (a model rating outputs written in its own style more
favorably). Two stronger candidates were tried first and ruled out with live
calls, not assumptions:

- `gpt-5.6-luna` — HTTP 500 "Internal server error", reproduced on a second
  attempt. Not usable on this endpoint currently.
- `grok-4.6` — HTTP 401 "Model grok-4.6 is not supported for format
  oa-compat". This is a structural incompatibility (Grok isn't served via
  this OpenAI-compatible path on the Go plan), not an auth problem.
- `qwen3.8-max` — HTTP 200, clean completion. **Selected as judge.** It's
  the strongest confirmed-working general-reasoning model on the plan that
  isn't one of the three models under test, and it's from a distinct model
  family (Alibaba/Qwen) relative to Moonshot (Kimi), DeepSeek, and Zhipu
  (GLM) — reducing shared-lineage bias as well as self-preference bias.

### Open item: reasoning-effort parameterization

Whether this endpoint exposes a standard `reasoning_effort` request
parameter (as opposed to needing per-model prompt-based control) has **not
yet been verified with a live call**. This will be confirmed as part of
building `scripts/run_generation.py`, and the confirmed mechanism will be
recorded in `config/models.yaml` (`reasoning_effort_param_verified`) once
known. Until then, treat the `reasoning_effort_conditions: [high, none]`
entry in that file as the target design, not a confirmed working mechanism.

## Dataset

Source: [eth-lre/mathtutorbench](https://github.com/eth-lre/mathtutorbench)
(GitHub, not a Hugging Face Hub dataset — confirmed by Hub search returning
no matches for `eth-lre/mathtutorbench` or `MathTutorBench`).
`data/fetch_dataset.py` (not yet implemented) will pull the repo directly,
isolate the hard-scaffolding subset, and record the repository's actual
license text here rather than assuming one.

**License (as found verbatim in the source repo's README, fetched
2026-08-29 — see `data/raw/LICENSE_NOTICE.txt` for the exact text):** the
repo's badge at the top declares **CC BY 4.0**, but the footer text declares
**CC BY-SA 4.0** — these are not the same license (ShareAlike adds a
copyleft requirement). The source repo itself is inconsistent about which
applies. Treat this as **CC BY-SA 4.0** (the more restrictive of the two, and
the one stated in prose rather than just a badge) until upstream clarifies,
and attribute the original MathTutorBench authors before any public sharing
of results or derived data.

## Folder structure

```
config/models.yaml      resolved model IDs, base URL, judge pick (this file is authoritative)
.env.example             OPENCODE_GO_API_KEY placeholder
data/fetch_dataset.py    pulls the dataset, isolates hard-scaffolding subset       [not yet implemented]
harbor/                  minimal Harbor task adapter (Instruction/Environment/Verifier) [not yet implemented]
scripts/run_generation.py   calls the 3 test models: 327 dialogs x 3 trials x 2 reasoning settings [not yet implemented]
scripts/run_judge.py        scores every generation with the judge model           [not yet implemented]
scripts/aggregate_stats.py  mean + 95% CI per model per reasoning setting, chart    [not yet implemented]
results/                 gitignored; generated at runtime
```

## Running (planned)

Not yet implemented. Will support `--dry-run` (5 dialogs x 1 trial) before
any full run, resume-from-checkpoint, retry-with-backoff, and a running
cost/request counter that warns at 80% of a user-specified cap.

## Statistics (planned)

Per model per reasoning-effort setting: `mean ± 1.96 * stddev / sqrt(n)`
(standard 95% CI under a normal approximation), computed over all
`dialogs x trials` judge scores for that model/setting. Formula and code
will live in `scripts/aggregate_stats.py`.

## Known limitations

- Judge-prompt sensitivity: LLM-judge scores are sensitive to prompt wording.
  The exact prompt used is logged verbatim to `results/judge_prompt.txt` on
  every run specifically so this sensitivity is documented, not hidden.
- Different judge model and prompt than Braintrust's original (theirs isn't
  public) — see "Why this won't match" above.
- All calls (test models + judge) share one OpenCode Go quota; a long run of
  one component reduces headroom for the others.
