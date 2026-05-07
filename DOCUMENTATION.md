# Trend Scout — Project Documentation

**A multi-agent trend-briefing generator for DRYKORN**

| | |
|---|---|
| **Course** | Foundations of Agentic AI |
| **Author** | Niklas Geier |
| **Framework applied** | Agentic Development Lifecycle (ADLC) — Day 1 |
| **Final stack** | Python · Gemini 2.5 Flash · `google_search` grounding · multimodal validation · Streamlit · `asyncio` |

---

## Executive Summary

Trend Scout generates a fashion-trend briefing in roughly 30–60 seconds. A user enters a season (e.g. `FW26`) and target group (e.g. `Women's Premium Casual`); a planner decomposes the request into per-agent research angles; the user reviews and approves the plan (HITL gate); N research agents fan out in parallel — each with `google_search` grounding plus a per-agent evaluator-optimizer loop; a Tree-of-Thought synthesis produces three full briefings under different lenses and a picker chooses the strongest; a Reflection critic reads the chosen briefing and triggers one revision pass if the draft has issues; finally a multimodal validator filters the moodboard images so only on-topic visuals reach the UI.

Briefings are persisted to `~/.trend-scout/history/` for reload from the sidebar; identical inputs return the cached run instead of hitting the API.

This document tells the story along the six stations of the **Agentic Development Lifecycle (ADLC)**. Trend Scout walked the cycle several times — the journey section at the end traces the laps that shaped the current architecture.

---

## The ADLC Cycle

```
                ┌──────────────────────────┐
                │   1. Goal Definition     │
                └────────────┬─────────────┘
                             ▼
       ┌──────────────────────────────────────────┐
       │  2. Product Requirements Document (PRD)  │
       └────────────────────┬─────────────────────┘
                            ▼
              ┌─────────────────────────┐
              │   3. Write Skills       │
              └────────────┬────────────┘
                           ▼
            ┌──────────────────────────────┐
            │   4. Orchestrate Agents      │
            └────────────┬─────────────────┘
                         ▼
        ┌─────────────────────────────────────┐
        │   5. Monitoring & Feedback          │
        └────────────┬────────────────────────┘
                     ▼
       ┌──────────────────────────────────────────┐
       │  6. Continuous Execution & Deployment    │
       └────────────────────┬─────────────────────┘
                            └──────► loops back to (1)
```

---

## Station 1 — Goal Definition

DRYKORN's trend team produces seasonal trend briefings manually. Friction:

- Sources are scattered: Vogue, Pinterest, Pantone, Business of Fashion, competitor lookbooks.
- Manual research takes 4–8 hours per briefing.
- Output is subjective — different team members produce different briefings from the same brief.

**Goal:** Generate a defensible, source-backed trend briefing for any (season, target-group) combination in under one minute, using only free APIs. *Defensible* is the load-bearing word — every claim has to be linked to a real source the user can click.

**Constraints:**

- Free-tier APIs only (no credit card required for the dev loop)
- Single-laptop deploy — no cloud infrastructure
- Markdown output, pasteable into Notion / Google Docs / email

---

## Station 2 — Product Requirements Document (PRD)

### Stakeholders

| Role | Need |
|---|---|
| **Trend designer (primary user)** | Fast, source-backed input for collection planning |
| **Senior strategist** | Consolidated executive summary they can take to a meeting |
| **Sourcing/buying** | Concrete color recommendations with hex codes |
| **Course examiner** | Demonstrable application of ADLC + agent architecture patterns |

### Functional requirements

| ID | Requirement | Status |
|---|---|---|
| F1 | Accept text input for `season` and `target_group` | ✓ |
| F2 | Planner proposes per-agent research angles before research starts | ✓ |
| F3 | User reviews and edits the plan (HITL gate) before approval | ✓ |
| F4 | User can add custom on-the-fly agents (Sustainability, Material, Regional, …) | ✓ |
| F5 | Research agents run in parallel via `asyncio.gather` | ✓ |
| F6 | Each agent uses live web search via `google_search` grounding | ✓ |
| F7 | Each agent has an evaluator-optimizer loop that revises low-scoring research | ✓ |
| F8 | Synthesis is Tree-of-Thought: 3 drafts under different lenses, picker chooses best | ✓ |
| F9 | Briefing has 4 fixed sections: Executive Summary, Key Themes, Recommended Colors, Risk Assessment | ✓ |
| F10 | Recommended colors are emitted with hex codes and rendered as swatches with paired imagery | ✓ |
| F11 | Live status per agent during the run (running / done / elapsed time / eval score) | ✓ |
| F12 | Sources rendered as clickable cards with domain favicon and og:image | ✓ |
| F13 | Multimodal validator filters the moodboard so only on-topic images reach the UI | ✓ |
| F14 | Reflection critic reviews the picked briefing; if issues, one revision pass | ✓ |
| F15 | Briefings persisted to disk under `~/.trend-scout/history/` and reloadable from sidebar | ✓ |
| F16 | Cache: identical (season, target, agent setup) returns the previous briefing without API calls | ✓ |
| F17 | Speed-toggle: Fast (max 2 eval rounds) vs Quality (max 6) | ✓ |
| F18 | Final briefing exportable as Markdown and printable HTML (Browser → Save as PDF) | ✓ |

### Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NF1 | Total runtime ≤ 60 seconds typical | ✓ |
| NF2 | Only one external API key required (`GEMINI_API_KEY`) | ✓ |
| NF3 | Free tier of the chosen API is sufficient for development & demo | ✓ |
| NF4 | Pragmatic module layout — coarse files by topic, not micro-split | ✓ (7-file split) |
| NF5 | Light- and dark-mode support | ✓ |
| NF6 | DRYKORN-on-brand visual identity (monochrome, editorial, Inter font) | ✓ |
| NF7 | Hot-reload on code change for fast iteration | ✓ (Streamlit `runOnSave`) |

### Out of scope

- Persistence across sessions (no database, no history of past briefings).
- User authentication or per-user customisation.
- PDF export of the briefing (Markdown is the source of truth).
- Multilingual output (English only).
- Image generation (we use real og:images from research sources, not generated ones).

---

## Station 3 — Write Skills (the agents)

Eight LLM-driven roles, each with its own system prompt. They share the same Gemini client and async retry wrapper.

| Role | Prompt source | Tools | Purpose |
|---|---|---|---|
| **Planner** | `PLANNER_SYSTEM` | none | Decompose `(season, target)` into per-agent research angles + cross-cutting themes |
| **Researcher** (×N) | per-agent system from `AGENTS` dict | `google_search` | Produce 3-5 markdown findings per agent, grounded in live web sources |
| **Evaluator** (text-only) | `EVALUATOR_SYSTEM` | none | Score the researcher's output 1-10 on credibility, concreteness, season fit; reject if weak |
| **Synthesizer** ×3 | `SYNTHESIS_SYSTEM` + lens | none | Three full briefing drafts, each through a different lens (Commercial / Strategic / Signal-Strength) |
| **Picker** | `BRIEFING_PICKER_SYSTEM` | none | Select the strongest of the three drafts |
| **Reflection Critic** | `REFLECTION_CRITIC_SYSTEM` | none | Read the picked briefing and decide if a revision pass is needed |
| **Reflection Reviser** | `REFLECTION_REVISER_SYSTEM` | none | Rewrite the briefing addressing the critic's flagged issues — only if needed |
| **Gallery Validator** (multimodal) | `GALLERY_VALIDATOR_SYSTEM` | image input | Filter the moodboard pool — accept editorial/lookbook visuals, reject logos/UI/banners |

### The agents

| Agent | Domain | Source bias | Core deliverable |
|---|---|---|---|
| **Runway** | Editorial fashion | Vogue, Business of Fashion, Fashion Weeks | Silhouettes, materials, styling cues |
| **Social** | Mainstream / youth | TikTok, Pinterest, Instagram | Aesthetics, hashtags, micro-trends |
| **Color** | Forecasting | Pantone, WGSN | Hex codes + rationale |
| **Competitor** | Positioning | Closed, Marc O'Polo (DRYKORN-tier) | Collection strategies, assortment focus |
| **(custom)** | User-defined | User-defined | Sustainability, Material Innovation, Regional Market, … |

The four defaults give one editorial / one social / one craft / one competitive — independent, non-overlapping perspectives. Custom agents extend the topology at runtime through the HITL gate.

### Same code path, different prompts

Multi-agent here means *same code, different prompt*. `run_agent()` in [trend_scout/research.py](trend_scout/research.py) is one function — the system prompt and the user-approved query angles are what make Runway, Social, Color, Competitor, and any custom agent behave differently.

---

## Station 4 — Orchestrate Agents

### Topology

```
              [User Input: season + target group]
                            │
                            ▼
                       Planner LLM
                            │
                            ▼
                  ┌─────────────────┐
                  │   HITL Gate     │   ← user reviews / edits plan,
                  │ (plan review)   │     adds custom agents, approves
                  └────────┬────────┘
                           │
                           ▼
                   asyncio.gather
        ┌────────┬──────┬────────┬────────┬─────────┐
        ▼        ▼      ▼        ▼        ▼         ▼
     Runway   Social  Color  Competitor  Custom₁  Custom_N
        │        │      │        │         │        │
        │   each: research → eval → (revise) loop   │
        └────────┴──────┴────────┴────────┴────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   ToT Synthesis │   ← 3 drafts in parallel,
                  │   3 lenses + picker │   picker chooses winner
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   Multimodal    │   ← og:images downloaded,
                  │   Validator     │     scored against briefing,
                  └────────┬────────┘     filtered for moodboard
                           │
                           ▼
                     Trend Briefing
                + Moodboard + Color Cards
```

### Four agentic patterns combined

Trend Scout demonstrates four distinct course patterns in one pipeline:

1. **Planner-Executor** (Day 2 slide 15) — the Planner decomposes the request into per-agent angles before any research starts. The user can edit the plan (HITL).
2. **Evaluator-Optimizer** (Day 2 slides 33–37) — every research agent runs `research → evaluate → revise` until approved or `max_rounds` is hit. Low-scoring research is sent back with the evaluator's feedback.
3. **Tree-of-Thought** (Day 2 slide 13) — synthesis produces three competing briefing drafts under different lenses; a separate picker LLM scores them and selects the winner. All three drafts remain visible in the UI for transparency.
4. **Reflection** (Day 3 slides 12–13) — after the picker, a critic LLM reads the chosen briefing and decides whether a revision is needed. If yes, a reviser rewrites the briefing addressing the critic's flagged issues. Capped at one pass — no infinite loops.

### Two-track parallelism inside research

Within each agent's loop, the annotator-vs-citation-enrichment race that the original architecture used was eliminated — research now runs `researcher → (citation enrichment + evaluation in parallel) → revise`. The og:image scraping completes in the background while the evaluator scores text quality.

### Multimodal moodboard validator

After the briefing is picked, the system collects all unique og:image URLs from every agent's citations, downloads the bytes in parallel, sends all of them in a single multimodal request to Gemini with the briefing as context, and keeps only those tagged `ok` — capped at 15 for the final UI. URLs that won't load (Cloudflare bot-block, 403, missing `og:image`) drop out automatically — no filter math needed.

---

## Station 5 — Monitoring & Feedback

### What's observable

| Signal | Where | Why it's there |
|---|---|---|
| Per-agent state (`running` / `done`) | UI status block | Visualises the parallelism — central educational moment |
| Per-agent elapsed time + eval score + round count | UI status block | Surfaces which research domain is bottlenecking and which needed revision |
| 3 ToT drafts + picker reasoning | "Tree of Thought" expander | Transparent agent decision-making; the loser drafts stay visible |
| Source list per agent | Agent tab | Audit trail — "where did this finding come from?" |
| og:image per source | Source card | Editorial proof that sources are real, not faked |
| Multimodal moodboard | Below briefing card | Aggregated visual evidence, validated for relevance |
| Color palette swatches with paired imagery | Recommended-Colors section | Direct visual translation of the color recommendations |
| Run-stats footer | Page bottom | Total elapsed, API calls, evaluator rounds, sources |

### Source-trace pattern

Each agent emits citations from `response.candidates[0].grounding_metadata.grounding_chunks`. They get:

1. **Enriched in parallel** with og:image and og:title (much better titles than Gemini's grounding metadata returns)
2. **Passed into the synthesis prompt** as `**Sources:**` blocks per agent — synthesis sees the URLs, can attribute claims
3. **Aggregated into the moodboard pool** for the multimodal validator
4. **Rendered as clickable cards** in the per-agent tabs

The user can audit any claim within two clicks.

---

## Station 6 — Continuous Execution & Deployment

### Local dev loop

| Action | Tool / setting |
|---|---|
| Code change | File save → Streamlit `runOnSave = true` triggers automatic rerun |
| New theme | Edit `.streamlit/config.toml` → reload browser |
| New dependency | `pip install` → already isolated in `.venv` |
| New custom agent | Add via the HITL UI at runtime — no code change |

### Deployment path

For the course demo: local. For wider use:

- Streamlit Community Cloud (free tier): push to GitHub, connect via web UI, get a public URL like `trend-scout.streamlit.app`.
- Limitations of free tier: 1 GB RAM, sleeps after 7 days of inactivity, public source code (so secrets must use Streamlit secrets management).

### Limitations

| | |
|---|---|
| **Bot-blocked sources** | Vogue, BoF, Pinterest serve 403 to httpx → no og:image. The validator handles this gracefully (those URLs just drop out), but a moodboard's coverage depends on which domains the researcher cited. |
| **Streamlit FOUC** | Custom CSS arrives after the React frontend's first render. ~0.3s flash on initial load. Cannot be eliminated without patching Streamlit. |
| **Free-tier rate limits** | `gemini-2.5-flash` is in the low hundreds of RPD. Roughly 20–40 demo runs per day on a single key. |
| **No retry on agent failure** | A failed agent fails the whole run. Fast-fail preferred over silent partial results for demos. |
| **No caching layer** | Repeated identical runs hit the API again. Deliberately omitted to keep behaviour predictable. |
| **Event-loop reuse on Windows** | Streamlit's `asyncio.run()` per phase requires per-loop client reinitialisation; handled in `llm.get_client()`. |

---

## Project Journey

The ADLC isn't a one-shot waterfall — it's a loop. Trend Scout went around it several times. Each lap removed a class of complexity and replaced it with a simpler primitive.

### Lap 1 — Anthropic + Tavily, four agents

Initial cut: SQLite cache for Tavily searches, structured Pydantic outputs, separate `prompts/` directory, full tool-use schemas via Anthropic. **Killed** because Tavily required a separate API key — violated the *no paid third-party APIs* constraint.

### Lap 2 — OpenAI Responses API + native `web_search`

Same agents, prompts in a Python dict, single-file goal. Eliminated the Tavily plumbing using OpenAI's native `web_search` tool. **Killed** because OpenAI requires a credit card; the user had none.

### Lap 3 — Gemini API + `google_search` grounding (single-file)

Same architecture, SDK swap from `openai` to `google-genai`. Added og:image scraping for the moodboard via a parallel `asyncio.gather`. Result was ~525 lines, single file, working but coarse.

### Lap 4 — 7-file refactor + planner-executor + multimodal evaluator

Split the monolith into a `trend_scout/` package by topic (`config`, `prompts`, `llm`, `research`, `synthesis`, `ui`). Added a Planner stage with HITL gate. Per-agent evaluator-optimizer loop introduced. First multimodal experiment: per-finding visual validation, with annotator + brand-keyword theme-matching pipeline.

### Lap 5 — Tree-of-Thought + Custom Agents

Synthesis became 3 drafts under different lenses (`Commercial`, `Strategic`, `Signal-Strength`) with a picker LLM choosing the winner. UI gained the ToT expander showing all three drafts. Custom-agent feature added via the HITL UI.

### Lap 6 — Image-pipeline cleanup + Moodboard validator

The original per-finding multimodal pipeline (annotator → og:image fetch → multimodal eval → brand-keyword theme-match) had three filter layers that often dropped 100% of the images before they reached the UI. Replaced with a single, simpler stage: collect all og:images, run one multimodal validator pass against the briefing, render whatever survives. Moodboard renders below the briefing instead of being matched per-theme. Color cards now carry a paired image from the Color-agent's citations (or fall back to the gallery pool when Color sources bot-block). Result: less code, fewer LLM calls per run, more images actually shown.

### Lap 7 — Day-3 reflection + History/Caching/Export

Adding the Day-3 patterns. **Reflection** (slides 12–13) became its own stage: a critic LLM reads the chosen briefing draft after the picker and flags concrete issues; if there are any, a reviser rewrites the briefing in one pass. **Persistent history** under `~/.trend-scout/history/` keeps every run on disk. **Caching** uses a hash over (season, target, agent specs) — repeat runs of the same query return the cached briefing without an API call. **HTML export** complements the Markdown download: a self-contained printable doc with embedded image URLs, ready to be saved as PDF from the browser. **Speed-toggle** in the sidebar (Fast / Quality) lets the user pick how many evaluator rounds an agent may run. **Pipeline-details expander** below the run summary surfaces validator counts, reflection verdict, and per-agent stats. Code-quality pass: stale UI texts updated, dead code removed, color-images now run through the validator for consistency.

### What the journey tells us about ADLC

The cycle is the right framing. **Each station only makes sense in the context of the others.** Goal definition without a PRD becomes wishlists. Skills without orchestration become disconnected scripts. Monitoring without deployment is invisible. The discipline of walking the loop — and being willing to walk it again when reality forces a pivot — is what kept Trend Scout converging instead of sprawling. The final code is shorter and clearer than after lap 1, despite doing more.

---

## Lessons Learned

1. **Multi-agent isn't an end in itself.** Parallelism only pays off when agents have independent domains. Splitting one task into four sub-tasks of the same domain just multiplies LLM cost without quality gain. The four-agent split (editorial / social / color / competitive) is non-negotiable for the value, not a stylistic choice.
2. **HITL is the cheapest reliability gain.** A 10-second plan-review checkpoint catches misframed research before any agent runs — saves more wall-clock time than any prompt-engineering tweak.
3. **Cascading filters quietly fail.** The first image pipeline had three filter layers; in practice they usually filtered the result down to nothing. One simple validator pass beats three theoretically-optimal ones that don't survive contact with reality.
4. **Native tool calling > custom API wrappers.** Lap 1 had ~200 lines of Tavily plumbing. Lap 6 has zero — Gemini's `google_search` does it server-side, including citations.
5. **The aggregation step is the most important one.** Without it, parallel agent outputs are just disjointed noise. The synthesis (and now the picker on top) is what makes the multi-agent system feel coherent.
6. **Free tier limits are real and immediate.** A production deployment needs a paid API tier or a multi-key rotation strategy from day one.
7. **The ADLC cycle works.** Walking it six times for one project sounds inefficient, but each lap removed complexity and replaced it with a simpler primitive.

---

## Repository Layout

```
trend-scout/
├── streamlit_app.py        # UI shell: sidebar, idle/planned/done phases, final render
├── trend_scout/
│   ├── __init__.py
│   ├── config.py           # AGENTS dict, gallery caps, MAX_AGENT_ROUNDS
│   ├── prompts.py          # all system prompts (Planner, Researcher, Evaluator, Synthesis, Picker, Reflection-Critic/Reviser, Validator)
│   ├── llm.py              # Gemini client (per-loop cache), retry wrapper, citation enrichment, image-bytes fetch
│   ├── research.py         # Planner + per-agent research → eval → revise loop
│   ├── synthesis.py        # ToT drafts + picker + reflection + multimodal moodboard validator
│   ├── storage.py          # JSON history + hash-based cache (~/.trend-scout/history/)
│   ├── export.py           # HTML export (Browser → Save as PDF)
│   └── ui.py               # CSS + briefing-card + moodboard gallery + color cards
├── requirements.txt
├── .env / .env.example     # GEMINI_API_KEY only
├── .streamlit/config.toml  # theme.light + theme.dark, runOnSave, toolbarMode
├── README.md
├── DOCUMENTATION.md        # this file
├── Course_Day1.md          # course material extracted to Markdown
├── Course_Day2.md          # course material extracted to Markdown
├── Course_Day3.md          # course material extracted to Markdown
└── Trend_Scout_Presentation.pptx
```

---

## Setup & Run

```powershell
cd trend-scout
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env, set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)
streamlit run streamlit_app.py
```

Open http://localhost:8501.

---

## References

**Course material:**
- *Foundations of Agentic AI — Day 1*: ADLC framework, rule-based vs LLM-driven agents, autonomy maturity levels
- *Day 2 — Agent Architectures, Memory & Planning*: cognitive architecture, planning patterns (planner-executor, tree-of-thought), tool calling, evaluator-planner loops, safety & guardrails
- *Day 3 — Building Autonomous Agents & Tool-Using Systems*: tool execution, plan-as-JSON / plan-as-code, guardrails as code / as LLM judge, reflection loops, framework ecosystems (LangChain, CrewAI)

**APIs & libraries:**
- Gemini API: https://ai.google.dev/gemini-api/docs
- Gemini grounding (`google_search`): https://ai.google.dev/gemini-api/docs/grounding
- Google Gen AI Python SDK: https://googleapis.github.io/python-genai/
- Streamlit docs: https://docs.streamlit.io
- Open Graph protocol: https://ogp.me/

**Brands referenced:**
- DRYKORN (target): https://www.drykorn.com
- Closed, Marc O'Polo (competitors); Vogue, Business of Fashion (editorial); Pinterest, TikTok (social); Pantone, WGSN (forecasting)
