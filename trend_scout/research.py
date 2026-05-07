"""Planner + per-agent research pipeline.

Per-agent flow:
  1. researcher (google_search) → text + citations
  2. text-only evaluator scores it
  3. if rejected, revise (round loop)

Citation enrichment (og:image + better titles) runs in parallel with the
evaluator since it's independent of approval.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from typing import Callable

from google.genai import types

from .config import MAX_AGENT_ROUNDS, MODEL
from .llm import enrich_citations, extract_citations, generate_with_retry
from .prompts import EVALUATOR_SYSTEM, PLANNER_SYSTEM, RESEARCHER_USER_TEMPLATE


# ---------------------------------------------------------------- parse helpers

PLAN_HEADING_RE = re.compile(
    r"^(RUNWAY|SOCIAL|COLOR|COMPETITOR|CROSS_CUTTING)\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PLAN_HEADING_TO_KEY = {
    "RUNWAY": "Runway",
    "SOCIAL": "Social",
    "COLOR": "Color",
    "COMPETITOR": "Competitor",
    "CROSS_CUTTING": "CrossCutting",
}

EVAL_APPROVED_RE = re.compile(r"APPROVED:\s*(yes|no)", re.IGNORECASE)
EVAL_SCORE_RE = re.compile(r"SCORE:\s*(\d+)")
EVAL_FEEDBACK_RE = re.compile(r"FEEDBACK:\s*(.+)", re.DOTALL)


def parse_plan(text: str) -> dict[str, list[str]]:
    """Parse the planner output into per-agent lists of research angles."""
    plan: dict[str, list[str]] = {
        "Runway": [], "Social": [], "Color": [], "Competitor": [], "CrossCutting": []
    }
    current: str | None = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = PLAN_HEADING_RE.match(line.strip())
        if m:
            current = _PLAN_HEADING_TO_KEY.get(m.group(1).upper())
            continue
        if current is None:
            continue
        s = line.strip()
        if s.startswith(("-", "*", "•")):
            entry = s.lstrip("-*• ").strip()
            if entry:
                plan[current].append(entry)
    return plan


def parse_evaluation(text: str) -> dict:
    a = EVAL_APPROVED_RE.search(text or "")
    s = EVAL_SCORE_RE.search(text or "")
    f = EVAL_FEEDBACK_RE.search(text or "")
    return {
        "approved": bool(a and a.group(1).lower() == "yes"),
        "score": int(s.group(1)) if s else 5,
        "feedback": f.group(1).strip() if f else "",
    }


# ---------------------------------------------------------------- LLM calls


async def run_planner(season: str, target: str) -> dict[str, list[str]]:
    """Decompose the season+target request into per-agent research angles."""
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Season: {season}\n"
        f"Target group: {target}\n\n"
        "Generate the research plan for these inputs."
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=PLANNER_SYSTEM),
    )
    return parse_plan(response.text or "")


async def _evaluate_research(
    name: str, text: str, citations: list[dict], season: str, target: str
) -> dict:
    """Text-only evaluator-optimizer pass."""
    sources_block = (
        "\n".join(f"- {c['title']} ({c['url']})" for c in citations) or "(no sources)"
    )
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Agent role: {name}\n"
        f"Season: {season}\n"
        f"Target group: {target}\n\n"
        f"Research output:\n{text}\n\n"
        f"Cited sources:\n{sources_block}"
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=EVALUATOR_SYSTEM),
    )
    return parse_evaluation(response.text or "")


async def run_agent(
    name: str,
    system: str,
    season: str,
    target: str,
    plan_queries: list[str] | None = None,
    max_rounds: int = MAX_AGENT_ROUNDS,
) -> dict:
    """Per-agent loop: research → text-eval → revise.

    Returns:
      {
        "name": str,
        "text": str,                  # final researcher markdown
        "citations": [enriched dicts with url/title/image],
        "evaluation": {approved, score, feedback, round},
      }
    """
    feedback: str | None = None
    text = ""
    citations: list[dict] = []
    evaluation: dict = {"approved": True, "score": 0, "feedback": "", "round": 0}

    for round_num in range(1, max_rounds + 1):
        today = date.today().isoformat()
        user = (
            f"Today's date: {today}\n"
            f"Season: {season}\n"
            f"Target group: {target}\n\n"
        )
        if plan_queries:
            angles = "\n".join(f"- {q}" for q in plan_queries)
            user += (
                "User-approved research angles for this agent:\n"
                f"{angles}\n\n"
                "Cover these angles in your findings. You may surface adjacent findings "
                "if they're directly relevant.\n\n"
            )
        user += RESEARCHER_USER_TEMPLATE
        if feedback:
            user += (
                f"\n\nIMPORTANT: a previous version of your research was REJECTED "
                f"by the quality evaluator with this feedback:\n\n{feedback}\n\n"
                "Address these issues directly in this revised research."
            )

        # 1. Research with google_search
        response = await generate_with_retry(
            model=MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = response.text or ""
        raw_citations = extract_citations(response)

        # 2. Enrich citations (og:image, og:title) and evaluate in parallel
        enrich_task = asyncio.create_task(enrich_citations(raw_citations))
        eval_task = asyncio.create_task(
            _evaluate_research(name, text, raw_citations, season, target)
        )
        citations = await enrich_task
        evaluation = await eval_task
        evaluation["round"] = round_num

        if evaluation["approved"]:
            break
        feedback = evaluation["feedback"]

    return {
        "name": name,
        "text": text,
        "citations": citations,
        "evaluation": evaluation,
    }


async def run_research_phase(
    season: str,
    target: str,
    agent_specs: list[tuple[str, str, list[str] | None]],
    on_agent_done: Callable[[str, float, dict], None],
    max_rounds: int = MAX_AGENT_ROUNDS,
) -> list[dict]:
    """Phase 1: each agent in agent_specs runs in parallel with its full
    research → text-eval loop. Order of returned outputs matches the order
    of agent_specs (not completion order)."""
    t0 = time.perf_counter()
    tasks = [
        asyncio.create_task(
            run_agent(spec_name, system_prompt, season, target, queries, max_rounds)
        )
        for spec_name, system_prompt, queries in agent_specs
    ]

    outputs: list[dict] = []
    for task in asyncio.as_completed(tasks):
        result = await task
        outputs.append(result)
        on_agent_done(
            result["name"],
            time.perf_counter() - t0,
            result["evaluation"],
        )

    name_order = {spec[0]: i for i, spec in enumerate(agent_specs)}
    outputs.sort(key=lambda o: name_order.get(o["name"], 999))
    return outputs
