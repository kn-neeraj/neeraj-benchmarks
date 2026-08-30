"""Minimal Harbor-style task adapter for the hard-scaffolding task.

This is pure text generation - the model reads a problem + partial dialog
and writes the next teacher turn. There is no code execution and nothing to
sandbox, so Environment is a no-op. Verifier delegates scoring to the judge
model via OpenCodeGoClient rather than a rule-based checker, since teacher-turn
quality can't be verified structurally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import re

from scripts.common import OpenCodeGoClient, truncate_at_stop

# The OpenCode Go proxy's server-side stop-string application for kimi-k3
# (confirmed via a bare curl call with no client-side processing involved)
# leaks a single stray letter immediately before the stop match, e.g.
# "...10 spoons.e" right before where "Teacher:" would have started. This
# strips that one artifact letter; it's a narrow pattern (punctuation
# immediately followed by exactly one trailing lowercase letter with no
# space) so it won't touch real short trailing words.
_TRAILING_ARTIFACT_RE = re.compile(r"([.!?])[a-z]$")


def _strip_stop_artifact(text: str) -> str:
    return _TRAILING_ARTIFACT_RE.sub(r"\1", text)

SYSTEM_PROMPT_TEMPLATE = (
    "You are an experienced math teacher and you are going to respond to a "
    "student in a useful and caring way. The student is trying to solve the "
    "following problem.\n"
    "Problem: {question}\n"
    "Conversation:\n"
    "{dialog_history}\n"
    "Write only the next teacher turn, in at most two sentences. Guide the "
    "student with a hint, question, or nudge - do NOT state or give away the "
    "final numeric answer to the problem.\n"
    "Teacher (maximum two sentences): "
)

STOP_SEQUENCES = ["Student:", "\n\n", "Teacher:"]

JUDGE_PROMPT_TEMPLATE = (
    "You are grading a math tutoring dialog. A student is working through the "
    "problem below with a teacher. You will see the problem, the conversation so "
    "far, the teacher's ACTUAL human response, and a CANDIDATE response written "
    "by a different teacher for the same turn.\n\n"
    "Problem: {question}\n"
    "Reference solution (for your own context only - do not require the teacher "
    "turn to reveal this): {reference_solution}\n\n"
    "Conversation so far:\n{dialog_history}\n\n"
    "ACTUAL human teacher response: {ground_truth_response}\n\n"
    "CANDIDATE teacher response: {candidate_response}\n\n"
    "Score the CANDIDATE response from 0.0 to 1.0 on how well it serves as the "
    "next teacher turn, judged AGAINST the actual human response as the "
    "reference point. A score of 0.50 means the candidate is judged equal in "
    "quality to the actual human response. Higher than 0.50 means better than "
    "the human response; lower means worse. Consider: does it give a helpful "
    "nudge, question, or hint (not the full answer)? Is it at most two "
    "sentences? Is it appropriate given the conversation so far? Do not reward "
    "responses that reveal the final answer.\n\n"
    "Respond with ONLY a JSON object of the exact form "
    '{{"score": <float between 0.0 and 1.0>, "rationale": "<one sentence>"}}, '
    "with no other text."
)


@dataclass
class Instruction:
    dialog_id: int
    question: str
    dialog_history: str
    reference_solution: str
    ground_truth_response: str

    def render_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            question=self.question, dialog_history=self.dialog_history
        )

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Instruction":
        return cls(
            dialog_id=row["dialog_id"],
            question=row["question"],
            dialog_history=row["dialog_history"],
            reference_solution=row["reference_solution"],
            ground_truth_response=row["ground_truth_response"],
        )


class Environment:
    """No-op: this task is pure text generation, nothing to sandbox."""

    def setup(self) -> None:
        pass

    def teardown(self) -> None:
        pass


class Verifier:
    def __init__(self, judge_client: OpenCodeGoClient, judge_model: str):
        self.judge_client = judge_client
        self.judge_model = judge_model

    def score(self, instruction: Instruction, candidate_response: str) -> Dict[str, Any]:
        import json as _json

        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=instruction.question,
            reference_solution=instruction.reference_solution,
            dialog_history=instruction.dialog_history,
            ground_truth_response=instruction.ground_truth_response,
            candidate_response=candidate_response,
        )
        # reasoning_effort="none": with it omitted, qwen3.8-max was observed
        # taking 15+ minutes on this judge prompt (long reasoning trace before
        # ever emitting the JSON verdict) - confirmed by killing a hung run and
        # inspecting the open connection. A judge verdict doesn't need that.
        result = self.judge_client.chat(
            model=self.judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300,
            reasoning_effort="none",
        )
        raw = result["content"]
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            parsed = _json.loads(raw[start:end])
            judge_score = float(parsed["score"])
            judge_rationale = str(parsed.get("rationale", ""))
        except (ValueError, KeyError, IndexError):
            judge_score = None
            judge_rationale = f"PARSE_ERROR: {raw[:300]}"

        return {
            "judge_score": judge_score,
            "judge_rationale": judge_rationale,
            "judge_raw_response": raw,
            "judge_usage": result["usage"],
            "judge_latency_ms": result["latency_ms"],
        }


def generate_teacher_turn(
    client: OpenCodeGoClient,
    model: str,
    instruction: Instruction,
    reasoning_effort: Optional[str],
    max_tokens: int = 200,
) -> Dict[str, Any]:
    system_prompt = instruction.render_system_prompt()
    # Server-side stop only when reasoning is off. With reasoning enabled, the
    # stop-string match appears to scan the raw generation stream INCLUDING
    # the hidden reasoning trace - and a reasoning trace naturally drafts
    # candidate teacher lines and paragraph breaks, so it can contain
    # "Teacher:" or "\n\n" before the real answer ever starts, truncating the
    # response to nothing (confirmed: deepseek-v4-flash produced empty output
    # at wildly different completion_token counts, 101 to 736, with no token-
    # budget pattern - only explained by an early in-reasoning stop match).
    # The source MathTutorBench repo hit the same issue and works around it
    # the same way (models/completion_api.py: "Stop strings are applied after
    # the trace is removed, since they would otherwise fire inside the
    # reasoning"). Client-side truncation below still applies regardless.
    use_server_stop = reasoning_effort in (None, "none")
    result = client.chat(
        model=model,
        messages=[{"role": "user", "content": system_prompt}],
        temperature=0.7,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        stop=STOP_SEQUENCES if use_server_stop else None,
    )
    content = truncate_at_stop(result["content"], STOP_SEQUENCES)
    content = _strip_stop_artifact(content)
    result["content"] = content
    return result
