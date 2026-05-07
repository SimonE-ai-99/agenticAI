"""Trend Scout — Streamlit entry.

Thin UI shell: sidebar inputs, three phases (idle → planned → done), and the
final results render. All domain logic lives in the trend_scout/ package.

Run:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import asyncio
import os
import time

import streamlit as st
from dotenv import load_dotenv

from trend_scout.config import AGENTS, MODEL
from trend_scout.llm import generate_agent_spec, validate_input
from trend_scout.mails import draft_emails, is_valid_email, send_smtp_emails
from trend_scout.memory import (
    load_agent_library,
    load_profile,
    load_tones,
    render_profile_for_prompt,
    render_tones_block,
    save_agent_library,
    save_profile,
    save_tones,
)
from trend_scout.pdf import briefing_to_pdf
from trend_scout.research import run_planner
from trend_scout.storage import (
    compute_input_hash,
    delete_run,
    find_cached,
    list_runs,
    load_run,
    save_run,
)
from trend_scout.synthesis import run_briefing
from trend_scout.ui import (
    CSS_STYLE,
    add_custom_agent,
    remove_custom_agent,
    render_briefing_card,
    render_image_gallery,
    render_sources,
)


# Sidebar-Hints — pure UI strings, kept here so config.py stays domain-only.
AGENT_SIDEBAR_HINTS: dict[str, str] = {
    "Runway": "catwalks, editorials",
    "Social": "TikTok, Pinterest, Instagram",
    "Color": "Pantone, WGSN, forecasts",
    "Competitor": "Closed, Marc O'Polo",
}

load_dotenv()


# -------------------------------------------------------------------- UI shell

st.set_page_config(
    page_title="Trend Scout",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS_STYLE, unsafe_allow_html=True)


# -------------------------------------------------------------------- Sidebar

with st.sidebar:
    st.markdown('<div class="ts-eyebrow">Input</div>', unsafe_allow_html=True)
    season = st.text_input("Season", value="FW26", help="e.g. FW26, SS26")
    target = st.text_input("Target group", value="Women's Premium Casual")
    mode = st.radio(
        "Mode",
        ["Fast", "Quality"],
        index=1,
        horizontal=True,
        help="Fast: max 2 evaluator rounds per agent. Quality: max 6 (default).",
    )
    use_cache = st.checkbox(
        "Use cached briefing if available",
        value=True,
        help="If the same season + target + agent setup was run before, "
        "load the previous briefing instead of hitting the API again.",
    )
    st.write("")
    run_btn = st.button("Generate briefing", type="primary", use_container_width=True)

    # History — past runs, click to reload
    history_records = list_runs(limit=15)
    if history_records:
        st.markdown('<hr class="ts-rule"/>', unsafe_allow_html=True)
        with st.expander(f"History ({len(history_records)})"):
            for rec in history_records:
                ts = rec.get("timestamp", "")[:16].replace("T", " ")
                meta_parts: list[str] = [ts]
                if rec.get("mode"):
                    meta_parts.append(rec["mode"])
                if rec.get("agents_count"):
                    meta_parts.append(f"{rec['agents_count']} agents")
                if rec.get("sources"):
                    meta_parts.append(f"{rec['sources']} sources")
                meta_line = " · ".join(meta_parts)

                cols = st.columns([5, 1])
                with cols[0]:
                    if st.button(
                        f"{rec['season']} · {rec['target']}",
                        key=f"hist_load_{rec['id']}",
                        use_container_width=True,
                    ):
                        st.session_state.pending_history_load = rec["id"]
                        st.rerun()
                    st.markdown(
                        f'<div class="ts-history-meta">{meta_line}</div>',
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button(
                        "✕",
                        key=f"hist_del_{rec['id']}",
                        help="Delete",
                        use_container_width=True,
                    ):
                        delete_run(rec["id"])
                        st.rerun()

    st.markdown('<hr class="ts-rule"/>', unsafe_allow_html=True)
    st.markdown('<div class="ts-eyebrow">Architecture</div>', unsafe_allow_html=True)
    agent_lines = "\n".join(
        f"- **{name}** &nbsp;·&nbsp; {hint}"
        for name, hint in AGENT_SIDEBAR_HINTS.items()
    )
    st.markdown(
        "**Planner** decomposes the request into per-agent angles.\n\n"
        "**HITL gate** — review the plan, edit angles, drop or **add custom agents**, "
        "then approve.\n\n"
        "**N research agents** in parallel, each with `google_search` + a "
        "text-only evaluator-optimizer loop:\n\n"
        f"{agent_lines}\n"
        "- **(custom)** &nbsp;·&nbsp; Sustainability, Material, Regional, ...\n\n"
        "**Tree-of-Thought synthesis** — three drafts under different lenses, "
        "picker chooses the strongest.\n\n"
        "**Multimodal validator** filters the moodboard so only on-topic images "
        "reach the UI.\n\n"
        "**Reflection** revises the final briefing if the self-critic spots issues."
    )
    st.markdown(f'<div class="ts-meta">Model · `{MODEL}`</div>', unsafe_allow_html=True)


# -------------------------------------------------------------------- Header

st.markdown('<div class="ts-eyebrow">Trend Briefing</div>', unsafe_allow_html=True)
st.markdown('<h1>Trend Scout</h1>', unsafe_allow_html=True)
st.markdown(
    '<div class="ts-meta">Planner → HITL gate → N parallel researchers '
    '(google_search + text-only evaluator-optimizer loop) → ToT synthesis '
    '→ multimodal moodboard validator → reflection</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="ts-rule"/>', unsafe_allow_html=True)


# -------------------------------------------------------------------- Long-term memory
# Brand profile, mail tones, agent library — collapsed expander under the
# header, three tabs inside. Persisted to ~/.trend-scout/{profile,mail_tones,
# agents}.json. The pipeline reads them at run-start and injects them into
# the relevant LLM prompts.

with st.expander("Long-term memory", expanded=False):
    _profile = load_profile() or {}
    _tones = load_tones()
    _saved_agents = load_agent_library()

    mem_tabs = st.tabs([
        "Brand profile" + (" · set" if _profile else ""),
        f"Mail tones ({len(_tones)})",
        f"Agent library ({len(_saved_agents)})",
    ])

    # ---------- Brand profile
    with mem_tabs[0]:
        st.caption(
            "One profile that gets injected into every synthesis, picker, "
            "reflection, and mail agent call."
        )
        p_name = st.text_input(
            "Brand name", value=_profile.get("name", ""), key="bp_name"
        )
        p_pos = st.text_area(
            "Positioning",
            value=_profile.get("positioning", ""),
            key="bp_positioning",
            height=70,
            placeholder="e.g. premium-casual women's, German heritage, considered minimalism",
        )
        p_target = st.text_area(
            "Target customer",
            value=_profile.get("target_customer", ""),
            key="bp_target",
            height=70,
            placeholder="e.g. modern professional, 28-45, design-literate",
        )
        p_signature = st.text_area(
            "Signature pieces",
            value=_profile.get("signature_pieces", ""),
            key="bp_signature",
            height=70,
            placeholder="e.g. tailored coats, fluid trousers, fine knitwear",
        )
        p_color = st.text_area(
            "Color DNA",
            value=_profile.get("color_dna", ""),
            key="bp_color",
            height=60,
            placeholder="e.g. muted neutrals with occasional deep berry accents",
        )
        dos_donts_cols = st.columns(2)
        with dos_donts_cols[0]:
            p_dos_text = st.text_area(
                "Dos (one per line)",
                value="\n".join(_profile.get("dos", []) or []),
                key="bp_dos",
                height=110,
                placeholder="- pile on craft details\n- highlight materials and origin",
            )
        with dos_donts_cols[1]:
            p_donts_text = st.text_area(
                "Don'ts (one per line)",
                value="\n".join(_profile.get("donts", []) or []),
                key="bp_donts",
                height=110,
                placeholder="- over-trendy logos\n- fast-fashion silhouettes",
            )
        p_notes = st.text_area(
            "Notes",
            value=_profile.get("notes", ""),
            key="bp_notes",
            height=60,
            placeholder="anything else worth carrying across briefings",
        )
        if st.button("Save brand profile", use_container_width=True, key="bp_save"):
            save_profile({
                "name": p_name.strip(),
                "positioning": p_pos.strip(),
                "target_customer": p_target.strip(),
                "signature_pieces": p_signature.strip(),
                "color_dna": p_color.strip(),
                "dos": [x.strip().lstrip("-*• ").strip() for x in p_dos_text.splitlines() if x.strip()],
                "donts": [x.strip().lstrip("-*• ").strip() for x in p_donts_text.splitlines() if x.strip()],
                "notes": p_notes.strip(),
            })
            st.toast("Brand profile saved.", icon="✅")

    # ---------- Mail tones
    with mem_tabs[1]:
        st.caption(
            "Per-role tone guidance for the mail agent. Keywords are matched "
            "case-insensitive against the recipient's role; first match wins, "
            "no match falls back to the system-prompt defaults."
        )
        if "tones_draft" not in st.session_state:
            st.session_state.tones_draft = list(_tones)
        tones_draft = st.session_state.tones_draft
        for i, t in enumerate(tones_draft):
            with st.container(border=True):
                cols = st.columns([5, 1])
                with cols[0]:
                    t["role_match"] = [
                        x.strip() for x in
                        st.text_input(
                            "Role keywords (comma-separated)",
                            value=", ".join(t.get("role_match", []) or []),
                            key=f"tone_kw_{i}",
                            placeholder="ceo, head of, geschäftsführer",
                        ).split(",")
                        if x.strip()
                    ]
                with cols[1]:
                    if st.button("✕", key=f"tone_rm_{i}", use_container_width=True):
                        tones_draft.pop(i)
                        st.session_state.tones_draft = tones_draft
                        # Widgets are keyed by index → after pop, the index
                        # of every following row shifts. Clear the cached
                        # widget values so the redraw picks up each row's
                        # actual content from `tones_draft`, not the stale
                        # next-row state Streamlit kept around.
                        for k in [k for k in st.session_state if k.startswith(("tone_kw_", "tone_text_"))]:
                            del st.session_state[k]
                        st.rerun()
                t["tone"] = st.text_area(
                    "Tone",
                    value=t.get("tone", ""),
                    key=f"tone_text_{i}",
                    height=70,
                    placeholder="e.g. concise, top-line opportunity first, no jargon, ≤120 words",
                )
        cols = st.columns(2)
        with cols[0]:
            if st.button("+ Add tone", use_container_width=True, key="tone_add"):
                tones_draft.append({"role_match": [], "tone": ""})
                st.session_state.tones_draft = tones_draft
                st.rerun()
        with cols[1]:
            if st.button("Save tones", use_container_width=True, key="tones_save"):
                cleaned = [
                    {"role_match": t["role_match"], "tone": t["tone"].strip()}
                    for t in tones_draft
                    if t.get("role_match") and t.get("tone", "").strip()
                ]
                save_tones(cleaned)
                st.session_state.tones_draft = cleaned
                st.toast(f"Saved {len(cleaned)} tone profile(s).", icon="✅")

    # ---------- Agent library
    with mem_tabs[2]:
        st.caption(
            "Custom agents persisted across runs. Pick one in Plan Review "
            "to spin it up without re-typing the prompt + angles."
        )
        if not _saved_agents:
            st.markdown(
                '<div class="ts-meta">No saved agents yet. Add one in Plan '
                'Review and click <strong>Save to library</strong>.</div>',
                unsafe_allow_html=True,
            )
        for i, agent in enumerate(_saved_agents):
            with st.container(border=True):
                cols = st.columns([5, 1])
                with cols[0]:
                    st.markdown(f"**{agent.get('name', '(unnamed)')}**")
                    st.markdown(
                        f'<div class="ts-history-meta">'
                        f'{agent.get("domain", "")} &nbsp;·&nbsp; '
                        f'{len(agent.get("angles") or [])} angles</div>',
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button("✕", key=f"lib_rm_{i}", use_container_width=True):
                        del _saved_agents[i]
                        save_agent_library(_saved_agents)
                        st.rerun()


# -------------------------------------------------------------------- State

if "phase" not in st.session_state:
    st.session_state.phase = "idle"          # idle | planned | done
    st.session_state.plan = None             # dict[agent_name, list[str]]
    st.session_state.briefing = None
    st.session_state.outputs = []            # list[dict] from run_agent
    st.session_state.run_stats = None
    st.session_state.tot_info = None         # Tree-of-Thought metadata
    st.session_state.custom_agents = []      # list[{id, name, prompt, queries_text}]
    st.session_state.ca_next_id = 0
    st.session_state.plan_approved = False   # gate between plan-review form and pipeline run


# -------------------------------------------------------------------- Pipeline status helpers

def _step_label(step: dict) -> str:
    """Headline of a step card: 'Step N · Name · 1.2s · note'."""
    parts = [f"Step {step['num']} · {step['name']}"]
    if step.get("duration") is not None:
        parts.append(f"{step['duration']:.1f}s")
    if step.get("note"):
        parts.append(step["note"])
    return " &nbsp;·&nbsp; ".join(parts)


def _sub_label(sub: dict) -> str:
    """Header for a nested sub-status: 'Label · 12.3s · note'."""
    parts = [sub["label"]]
    if sub.get("duration") is not None:
        parts.append(f"{sub['duration']:.1f}s")
    if sub.get("note"):
        parts.append(sub["note"])
    return " · ".join(parts)


def _render_sub_in_status(sub: dict) -> None:
    """Render a sub-step using the same lean Streamlit-native look as the
    top-level steps — nested `st.status` with spinner / checkmark / red-x.
    Pending subs render nothing so the user only sees what's actually
    happening or done."""
    sub_status = sub.get("status", "pending")
    if sub_status == "pending":
        return
    label = _sub_label(sub)
    if sub_status == "running":
        st.status(label, state="running", expanded=False)
    elif sub_status == "done":
        st.status(label, state="complete", expanded=False)
    elif sub_status == "error":
        st.status(label, state="error", expanded=False)
    elif sub_status == "waiting":
        st.status(label, state="running", expanded=False)


def _render_step_in_slot(slot, step: dict) -> None:
    """Render a single step *directly* into its slot (no container wrapper).
    Going via `slot.status(...)` instead of `slot.container() → st.status(...)`
    matters: the wrapped form makes Streamlit render a chunky outlined box
    with a heavy green check, while the direct form uses the lightweight
    inline spinner + small checkmark — same look as Step 3.

    Pending steps render *nothing* — the slot stays empty until the step
    actually starts. That way the user only sees what's currently happening,
    not a stack of greyed placeholders for what's coming."""
    status = step.get("status", "pending")
    subs = step.get("subs") or []

    if status == "pending":
        return

    label = _step_label(step)

    if status == "running":
        box = slot.status(label, state="running", expanded=bool(subs))
    elif status == "done":
        box = slot.status(label, state="complete", expanded=False)
    elif status == "error":
        box = slot.status(label, state="error", expanded=True)
    elif status == "waiting":
        # Native "waiting" state doesn't exist — running shows a spinner,
        # which is fine here because the gate is genuinely interactive.
        box = slot.status(label, state="running", expanded=True)
    else:
        return

    if subs:
        with box:
            for sub in subs:
                _render_sub_in_status(sub)


def _render_steps_inline(steps: list[dict]) -> None:
    """Render a list of steps as separate cards at the current Streamlit
    cursor position — one fresh `st.empty()` per step. Use for non-live
    renderings (rerun-fill, done-phase, history-load)."""
    for step in steps:
        _render_step_in_slot(st.empty(), step)


# Pending history load: triggered by a History-button click in the sidebar.
# We resolve it here at the top of the run so st.session_state is reshaped
# before any phase-conditional render runs.
if st.session_state.get("pending_history_load"):
    run_id = st.session_state.pop("pending_history_load")
    record = load_run(run_id)
    if record is not None:
        st.session_state.phase = "done"
        st.session_state.plan = record.get("plan")
        st.session_state.briefing = record.get("briefing")
        st.session_state.outputs = record.get("outputs", [])
        st.session_state.tot_info = record.get("tot_info")
        st.session_state.run_stats = record.get("run_stats")
        st.session_state.enabled_agents = record.get("enabled_agents", [])
        # Cached/loaded runs didn't go through this session's pipeline, so
        # don't show a stale status block.
        st.session_state.pop("pipeline_steps", None)
        # Pull the prebuilt PDF if the record has one — saves a re-build
        # (and the moodboard image refetch) on the result page.
        cached_pdf = record.get("pdf_bytes")
        if cached_pdf:
            st.session_state.pdf_bytes = cached_pdf
            st.session_state.pdf_for = (
                record.get("season"),
                record.get("target"),
                record.get("briefing"),
            )
        else:
            st.session_state.pop("pdf_bytes", None)
            st.session_state.pop("pdf_for", None)


# -------------------------------------------------------------------- Run

if run_btn:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        st.error("GEMINI_API_KEY is not set. Create a .env file or set the environment variable.")
        st.stop()

    st.session_state.phase = "idle"
    st.session_state.plan = None
    st.session_state.briefing = None
    st.session_state.outputs = []
    st.session_state.run_stats = None
    st.session_state.run_t0 = time.perf_counter()
    st.session_state.pipeline_steps = []
    st.session_state.plan_approved = False
    # Custom-Agents bleiben erhalten — User kann sie via "Remove"-Button selbst rauswerfen.
    # Wir resetten nur die Plan-Text-Cache-Keys der Default-Agents damit der Planner-
    # Output frisch eingefüllt wird.
    for _agent in AGENTS:
        st.session_state.pop(f"plan_text_{_agent}", None)
        st.session_state.pop(f"plan_inc_{_agent}", None)

    # Cache-Hit: gleiche (season, target, mode) Kombination wurde schon mal gerunnt
    # → direkt das gespeicherte Briefing zeigen, Planner + Pipeline überspringen.
    # Custom-Agents überspringen den Cache, da sie eine bewusste Erweiterung sind.
    if use_cache and not st.session_state.custom_agents:
        cached = find_cached(season, target, mode)
        if cached is not None:
            st.session_state.phase = "done"
            st.session_state.plan = cached.get("plan")
            st.session_state.briefing = cached.get("briefing")
            st.session_state.outputs = cached.get("outputs", [])
            st.session_state.tot_info = cached.get("tot_info")
            st.session_state.run_stats = cached.get("run_stats")
            st.session_state.enabled_agents = cached.get("enabled_agents", [])
            st.session_state.pop("pipeline_steps", None)
            cached_pdf = cached.get("pdf_bytes")
            if cached_pdf:
                st.session_state.pdf_bytes = cached_pdf
                st.session_state.pdf_for = (
                    cached.get("season"),
                    cached.get("target"),
                    cached.get("briefing"),
                )
            else:
                st.session_state.pop("pdf_bytes", None)
                st.session_state.pop("pdf_for", None)
            st.rerun()

    # Pre-allocate one st.empty() per step we will render in this frame.
    # Each step lives in its OWN slot so we can update it in place without
    # re-rendering the others (and without nesting in a container, which
    # would make Streamlit draw a chunky boxed-look instead of the lean
    # native status look).
    step_slot_1 = st.empty()
    step_slot_2 = st.empty()

    steps: list[dict] = [
        {"num": 1, "name": "Input validator", "status": "running"},
    ]
    _render_step_in_slot(step_slot_1, steps[0])

    # Step 1 — Input guardrail
    t0_step = time.perf_counter()
    try:
        verdict = asyncio.run(validate_input(season, target, MODEL))
    except Exception:
        verdict = {"valid": True, "reason": ""}
    dt_step = time.perf_counter() - t0_step
    if not verdict.get("valid", True):
        reason = verdict.get("reason") or "Inputs were rejected by the guardrail."
        steps[0].update({"status": "error", "duration": dt_step, "note": "rejected"})
        _render_step_in_slot(step_slot_1, steps[0])
        st.error(f"Input rejected: {reason}")
        st.session_state.pipeline_steps = steps
        st.stop()
    steps[0].update({"status": "done", "duration": dt_step, "note": "guardrail passed"})
    _render_step_in_slot(step_slot_1, steps[0])

    steps.append({"num": 2, "name": "Research planner", "status": "running"})
    _render_step_in_slot(step_slot_2, steps[1])

    # Step 2 — Planner
    t0_step = time.perf_counter()
    try:
        plan = asyncio.run(run_planner(season, target))
    except Exception as e:
        steps[1].update({"status": "error", "note": "planner error"})
        _render_step_in_slot(step_slot_2, steps[1])
        st.session_state.pipeline_steps = steps
        st.error(f"Planner error: {e}")
        st.exception(e)
        st.stop()
    dt_step = time.perf_counter() - t0_step
    steps[1].update({"status": "done", "duration": dt_step, "note": "angles generated"})
    _render_step_in_slot(step_slot_2, steps[1])
    # Step 3 (Plan review HITL) is NOT added here — the planned-phase block
    # below renders it as a live interactive card whose body is the entire
    # plan-review UI. When the user approves, the card collapses and Step 3
    # gets appended to pipeline_steps with status="done".

    st.session_state.plan = plan
    st.session_state.pipeline_steps = steps
    st.session_state.phase = "planned"


# -------------------------------------------------------------------- HITL plan review

if st.session_state.phase == "planned":
    plan = st.session_state.plan or {}
    # Steps 1+2 (always done by this point) — render only on reruns. In the
    # same frame as run_btn=True, the run_btn branch already painted them.
    if not run_btn:
        _render_steps_inline(st.session_state.get("pipeline_steps") or [])

    # Step 3 — split into two branches gated by the `plan_approved` flag:
    #   • not approved → render the plan-review form as a plain section. We
    #     deliberately do NOT wrap it in `st.status`, because Streamlit's
    #     status body has a default max-height for log-streaming use cases
    #     that clips long interactive forms (the user can't scroll the page
    #     past the inner cap, and ends up trapped inside an inner scrollbar).
    #   • approved → render Step 3 as a collapsed status-card alongside the
    #     other pipeline steps, then run the actual research+synthesis run.
    # The flag is flipped by the Approve button, persisted to session_state
    # so the rerun-driven transition between branches is clean.
    if not st.session_state.plan_approved:
        edited_plan: dict[str, list[str]] = {}
        enabled_agents: set[str] = set()
        custom_agent_specs: list[tuple[str, str, list[str] | None]] = []

        # Wrap the whole plan-review form in one outer card so the Step 3 header,
        # per-agent sub-blocks, custom-agent section and approve button read as
        # one cohesive panel (matches Step 1+2 status-card aesthetic).
        _step3_card = st.container(border=True)

        with _step3_card:
            st.markdown(
                '<div class="ts-section" style="margin-top:0;">'
                'Step 3 · Plan review (HITL)'
                '</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="ts-meta" style="margin-bottom:1rem;">'
                'Edit the research angles per agent or untick a domain to skip it. '
                'Cross-cutting themes are passed to the synthesis as additional context.'
                '</div>',
                unsafe_allow_html=True,
            )

        for agent_name in AGENTS.keys():
            text_key = f"plan_text_{agent_name}"
            if text_key not in st.session_state:
                st.session_state[text_key] = "\n".join(
                    f"- {q}" for q in plan.get(agent_name, [])
                )

            with _step3_card:
                st.markdown(
                    '<hr class="ts-rule" style="margin: 1rem 0 0.75rem 0;"/>',
                    unsafe_allow_html=True,
                )
                cols = st.columns([5, 1])
                with cols[0]:
                    st.markdown(
                        f'<div class="ts-eyebrow" style="margin-top:0;">{agent_name} agent</div>',
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    include = st.checkbox(
                        "Include",
                        value=True,
                        key=f"plan_inc_{agent_name}",
                        label_visibility="collapsed",
                    )
                edited_text = st.text_area(
                    f"Research angles for {agent_name}",
                    height=260,
                    key=text_key,
                    label_visibility="collapsed",
                    disabled=not include,
                )
                queries: list[str] = []
                for raw in edited_text.splitlines():
                    s = raw.strip().lstrip("-*• ").strip()
                    if s:
                        queries.append(s)
                edited_plan[agent_name] = queries
                if include:
                    enabled_agents.add(agent_name)

        if st.session_state.custom_agents:
            with _step3_card:
                st.markdown(
                    '<hr class="ts-rule" style="margin: 1.25rem 0 0.5rem 0;"/>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="ts-eyebrow" style="margin-top:0.75rem;">Custom agents (user-added)</div>',
                    unsafe_allow_html=True,
                )
        for ca in st.session_state.custom_agents:
            cid = ca["id"]
            with _step3_card:
                cols = st.columns([5, 1])
                with cols[0]:
                    ca_name = st.text_input(
                        "Agent name",
                        value=ca["name"],
                        key=f"ca_name_{cid}",
                        label_visibility="collapsed",
                        placeholder="Agent name (e.g. Sustainability)",
                    )
                with cols[1]:
                    st.button(
                        "Remove",
                        key=f"ca_rm_{cid}",
                        on_click=remove_custom_agent,
                        args=(cid,),
                    )
                ca_domain = st.text_input(
                    "Domain",
                    value=ca.get("domain", ""),
                    key=f"ca_domain_{cid}",
                    placeholder="e.g. Sustainability, Material Innovation, Y2K Streetwear",
                )
                gen_cols = st.columns(2)
                with gen_cols[0]:
                    if st.button(
                        "✨ Generate prompt + angles",
                        key=f"ca_gen_{cid}",
                        use_container_width=True,
                        disabled=not ca_domain.strip(),
                        help="Use the LLM to draft a system prompt and 3 research "
                        "angles for this domain, calibrated to your brand profile.",
                    ):
                        try:
                            with st.spinner("Generating agent spec ..."):
                                spec = asyncio.run(generate_agent_spec(
                                    ca_domain.strip(),
                                    MODEL,
                                    render_profile_for_prompt(load_profile()),
                                ))
                            if spec.get("prompt"):
                                ca["prompt"] = spec["prompt"]
                                st.session_state.pop(f"ca_prompt_{cid}", None)
                            if spec.get("angles"):
                                ca["queries_text"] = "\n".join(
                                    f"- {a}" for a in spec["angles"]
                                )
                                st.session_state.pop(f"ca_text_{cid}", None)
                            if not spec.get("prompt") and not spec.get("angles"):
                                # generate_agent_spec swallows network/parse
                                # errors and returns empty fields. Surface that
                                # so the user knows to retry instead of staring
                                # at an unchanged form.
                                st.warning(
                                    "Generator returned no content — try a "
                                    "more specific domain or rerun."
                                )
                            else:
                                st.rerun()
                        except Exception as e:
                            st.error(f"Generator failed: {e}")
                with gen_cols[1]:
                    if st.button(
                        "💾 Save to library",
                        key=f"ca_save_lib_{cid}",
                        use_container_width=True,
                        disabled=not (ca.get("name") or "").strip(),
                        help="Persist this agent so you can load it again "
                        "in future runs.",
                    ):
                        lib = load_agent_library()
                        # Dedupe by name — saving overwrites the previous entry.
                        lib = [a for a in lib if a.get("name") != ca.get("name")]
                        lib.append({
                            "name": (ca.get("name") or "").strip(),
                            "domain": ca_domain.strip(),
                            "prompt": ca.get("prompt", ""),
                            "angles": [
                                x.strip().lstrip("-*• ").strip()
                                for x in (ca.get("queries_text") or "").splitlines()
                                if x.strip()
                            ],
                        })
                        save_agent_library(lib)
                        st.toast(f"Saved '{ca.get('name')}' to library.", icon="✅")
                ca_prompt = st.text_area(
                    "Role / system prompt",
                    value=ca["prompt"],
                    height=90,
                    key=f"ca_prompt_{cid}",
                )
                ca_queries = st.text_area(
                    "Research angles (one per line)",
                    value=ca.get("queries_text", ""),
                    height=90,
                    key=f"ca_text_{cid}",
                    placeholder="- specific angle 1\n- specific angle 2",
                )
                ca["name"] = ca_name
                ca["domain"] = ca_domain
                ca["prompt"] = ca_prompt
                ca["queries_text"] = ca_queries
                queries_list: list[str] = []
                for raw in ca_queries.splitlines():
                    s = raw.strip().lstrip("-*• ").strip()
                    if s:
                        queries_list.append(s)
                if ca_name.strip():
                    custom_agent_specs.append((ca_name.strip(), ca_prompt, queries_list or None))
                    enabled_agents.add(ca_name.strip())
                    edited_plan[ca_name.strip()] = queries_list

        # Add / Load-from-library buttons side by side.
        _saved_agents = load_agent_library()
        with _step3_card:
            st.markdown(
                '<hr class="ts-rule" style="margin: 1.25rem 0 0.75rem 0;"/>',
                unsafe_allow_html=True,
            )
            if _saved_agents:
                add_cols = st.columns(2)
                with add_cols[0]:
                    st.button(
                        "+ Add agent",
                        on_click=add_custom_agent,
                        use_container_width=True,
                        key="ca_add_btn",
                    )
                with add_cols[1]:
                    lib_options = [""] + [a["name"] for a in _saved_agents]
                    chosen = st.selectbox(
                        "Load from library",
                        options=lib_options,
                        key="ca_lib_pick",
                        label_visibility="collapsed",
                    )
                    if chosen:
                        saved = next(a for a in _saved_agents if a["name"] == chosen)
                        cid = st.session_state.get("ca_next_id", 0)
                        st.session_state.ca_next_id = cid + 1
                        st.session_state.custom_agents.append({
                            "id": cid,
                            "name": saved.get("name", ""),
                            "domain": saved.get("domain", ""),
                            "prompt": saved.get("prompt", ""),
                            "queries_text": "\n".join(
                                f"- {a}" for a in (saved.get("angles") or [])
                            ),
                        })
                        # Reset the selectbox so picking the same entry again works.
                        st.session_state.pop("ca_lib_pick", None)
                        st.rerun()
            else:
                st.button(
                    "+ Add agent",
                    on_click=add_custom_agent,
                    use_container_width=True,
                    key="ca_add_btn",
                )

            edited_plan["CrossCutting"] = plan.get("CrossCutting", [])

            cross_cutting = plan.get("CrossCutting", [])
            if cross_cutting:
                st.markdown(
                    '<div class="ts-eyebrow" style="margin-top:1.5rem;">Cross-cutting themes</div>',
                    unsafe_allow_html=True,
                )
                for theme in cross_cutting:
                    st.markdown(f"- {theme}")

            st.write("")
            n_enabled = len(enabled_agents)
            approve_btn = st.button(
                f"Approve plan and run {n_enabled} agent{'s' if n_enabled != 1 else ''}",
                type="primary",
                disabled=n_enabled == 0,
                use_container_width=True,
            )

        if approve_btn:
            # Stash the approved-form state on session_state and rerun. The
            # next pass enters the pipeline branch below with a fresh frame
            # — no leftover form widgets above the progress trail.
            st.session_state.plan = edited_plan
            st.session_state.enabled_agents = list(enabled_agents)
            st.session_state.custom_agent_specs_to_run = custom_agent_specs
            st.session_state.cross_cutting_to_run = plan.get("CrossCutting", [])
            n_enabled = len(enabled_agents)
            st.session_state.plan_approval_note = (
                f"approved with {n_enabled} agent{'s' if n_enabled != 1 else ''}"
            )
            st.session_state.plan_approved = True
            st.rerun()

        # Form rendered, no approve yet — halt before the result section.
        st.stop()

    # ====================== Plan approved → pipeline run ======================
    # All inputs come from session_state; the form widgets that lived above
    # are no longer in the DOM, so the page is just a clean list of step
    # cards (Steps 1-2 from `_render_steps_inline`, then Step 3 done, then
    # Steps 4-6 progressing live).
    edited_plan = st.session_state.get("plan", {}) or {}
    enabled_agents_list = st.session_state.get("enabled_agents", []) or []
    custom_agent_specs = st.session_state.get("custom_agent_specs_to_run", []) or []
    cross_cutting = st.session_state.get("cross_cutting_to_run", []) or []
    approval_note = st.session_state.get("plan_approval_note", "")
    enabled_agents_set = set(enabled_agents_list)
    n_enabled = len(enabled_agents_list)

    agent_specs: list[tuple[str, str, list[str] | None]] = []
    for agent_name, system_prompt in AGENTS.items():
        if agent_name in enabled_agents_set:
            queries = edited_plan.get(agent_name) or None
            agent_specs.append((agent_name, system_prompt, queries))
    agent_specs.extend(custom_agent_specs)

    # Append Step 3 (done), Step 4 (running), Step 5 (pending) to
    # pipeline_steps if not already present. Idempotent so any rerun before
    # the synchronous pipeline call below doesn't duplicate cards.
    steps = st.session_state.get("pipeline_steps") or []
    if not any(s.get("num") == 3 for s in steps):
        steps.append({
            "num": 3,
            "name": "Plan review (HITL)",
            "status": "done",
            "note": approval_note,
        })
    if not any(s.get("num") == 4 for s in steps):
        agent_subs = [
            {"label": spec[0], "status": "running"} for spec in agent_specs
        ]
        steps.append({
            "num": 4,
            "name": "Research agents (parallel)",
            "status": "running",
            "subs": agent_subs,
        })
    if not any(s.get("num") == 5 for s in steps):
        SYNTHESIS_STAGES = [
            ("drafts", "Tree-of-Thought drafts (3 lenses)"),
            ("picker", "Picker selects strongest draft"),
            ("reflection", "Reflection critic + optional revision"),
            ("validator", "Multimodal moodboard validator"),
        ]
        synth_subs = [
            {"label": label, "status": "pending", "_key": key}
            for key, label in SYNTHESIS_STAGES
        ]
        steps.append({
            "num": 5,
            "name": "Synthesis",
            "status": "pending",
            "subs": synth_subs,
        })
    st.session_state.pipeline_steps = steps

    step3_idx = next(i for i, s in enumerate(steps) if s["num"] == 3)
    step4_idx = next(i for i, s in enumerate(steps) if s["num"] == 4)
    step5_idx = next(i for i, s in enumerate(steps) if s["num"] == 5)

    # One slot per step — same lean st.status look as Steps 1+2 above.
    step_slot_3 = st.empty()
    step_slot_4 = st.empty()
    step_slot_5 = st.empty()
    step_slot_6 = st.empty()

    _render_step_in_slot(step_slot_3, steps[step3_idx])
    _render_step_in_slot(step_slot_4, steps[step4_idx])
    _render_step_in_slot(step_slot_5, steps[step5_idx])

    def _refresh_step4_status() -> None:
        """Promote Step 4 to done once all agent subs are done."""
        step4 = steps[step4_idx]
        if all(sub["status"] == "done" for sub in step4["subs"]):
            step4["status"] = "done"
            step4["note"] = f"{len(step4['subs'])}/{len(step4['subs'])} agents"
            step5 = steps[step5_idx]
            step5["status"] = "running"
            if step5["subs"]:
                step5["subs"][0]["status"] = "running"
        else:
            done_n = sum(1 for s in step4["subs"] if s["status"] == "done")
            step4["note"] = f"{done_n}/{len(step4['subs'])} agents done"

    def on_agent_done(name: str, elapsed: float, evaluation: dict) -> None:
        for sub in steps[step4_idx]["subs"]:
            if sub["label"] == name:
                sub["status"] = "done"
                sub["duration"] = elapsed
                rounds = evaluation.get("round", 1)
                round_word = "round" if rounds == 1 else "rounds"
                sub["note"] = (
                    f"score {evaluation.get('score', 0)}/10 · "
                    f"{rounds} {round_word}"
                )
                break
        _refresh_step4_status()
        _render_step_in_slot(step_slot_4, steps[step4_idx])
        # Step 5 may have flipped from pending to running.
        _render_step_in_slot(step_slot_5, steps[step5_idx])

    def on_synthesis_stage(stage_name: str) -> None:
        step5 = steps[step5_idx]
        for i, sub in enumerate(step5["subs"]):
            if sub.get("_key") == stage_name:
                sub["status"] = "done"
                if i + 1 < len(step5["subs"]):
                    step5["subs"][i + 1]["status"] = "running"
                break
        if all(sub["status"] == "done" for sub in step5["subs"]):
            step5["status"] = "done"
        else:
            step5["status"] = "running"
        _render_step_in_slot(step_slot_5, steps[step5_idx])

    max_rounds = 2 if mode == "Fast" else 6
    input_hash = compute_input_hash(season, target, mode)

    # Long-term memory injection: pull the saved brand profile and let
    # synthesis / reflection / picker reason against it.
    brand_profile_block = render_profile_for_prompt(load_profile())

    try:
        briefing, outputs, tot_info = asyncio.run(
            run_briefing(
                season,
                target,
                on_agent_done,
                agent_specs,
                cross_cutting=cross_cutting,
                max_rounds=max_rounds,
                on_synthesis_stage=on_synthesis_stage,
                brand_profile_block=brand_profile_block,
            )
        )

        # Step 6 — Build the PDF as the final pipeline step. Done here in
        # the pipeline (not lazily on download click) so the user sees a
        # single, complete progress trail and the Download button is just
        # a download afterwards.
        pdf_step = {"num": 6, "name": "Build PDF", "status": "running"}
        steps.append(pdf_step)
        _render_step_in_slot(step_slot_6, pdf_step)
        t0_pdf = time.perf_counter()
        try:
            pdf_bytes = briefing_to_pdf(
                season=season,
                target=target,
                briefing_text=briefing,
                outputs=outputs,
                gallery_images=(tot_info or {}).get("gallery_images") or [],
            )
            pdf_step.update({
                "status": "done",
                "duration": time.perf_counter() - t0_pdf,
                "note": f"{len(pdf_bytes) / 1024:.0f} KB",
            })
            st.session_state.pdf_bytes = pdf_bytes
            st.session_state.pdf_for = (season, target, briefing)
        except Exception as e:
            pdf_step.update({
                "status": "error",
                "note": f"PDF build failed: {str(e)[:80]}",
            })
        _render_step_in_slot(step_slot_6, pdf_step)

        elapsed = time.perf_counter() - st.session_state.run_t0

        rounds_total = sum(o["evaluation"].get("round", 1) for o in outputs)
        sources_total = sum(len(o.get("citations") or []) for o in outputs)
        # API calls per run:
        # 1 input-validator + 1 planner + (researcher + evaluator) per round
        # + 3 ToT drafts + 1 picker + 1 reflection critic + (1 reviser if revised)
        # + 1 moodboard validator. PDF build is local, not an API call.
        revised = bool((tot_info.get("reflection") or {}).get("revised"))
        api_calls = (
            1 + 1 + rounds_total * 2 + 3 + 1 + 1 + 1
            + (1 if revised else 0)
        )

        st.session_state.briefing = briefing
        st.session_state.outputs = outputs
        st.session_state.tot_info = tot_info
        run_stats = {
            "elapsed": elapsed,
            "api_calls": api_calls,
            "sources": sources_total,
            "evaluator_rounds": rounds_total,
            "season": season,
            "target": target,
            "enabled_count": n_enabled,
            "mode": mode,
            "max_rounds": max_rounds,
        }
        st.session_state.run_stats = run_stats
        st.session_state.phase = "done"

        # Persist to history for caching + reload-from-sidebar.
        try:
            save_run(
                season=season,
                target=target,
                briefing=briefing,
                outputs=outputs,
                tot_info=tot_info,
                run_stats=run_stats,
                plan=edited_plan,
                enabled_agents=enabled_agents_list,
                input_hash=input_hash,
                pdf_bytes=st.session_state.get("pdf_bytes"),
            )
        except Exception:
            pass  # history is best-effort, don't break the UI on disk errors

        st.rerun()
    except Exception as e:
        # Pipeline crashed — flip the approval flag back so the next rerun
        # lands on the form again (user can edit + re-approve) instead of
        # re-executing the same failing pipeline on every interaction.
        st.session_state.plan_approved = False
        for s in steps:
            if s.get("status") == "running":
                s["status"] = "error"
                s["note"] = str(e)[:80]
                if s["num"] == 4:
                    _render_step_in_slot(step_slot_4, s)
                elif s["num"] == 5:
                    _render_step_in_slot(step_slot_5, s)
                elif s["num"] == 6:
                    _render_step_in_slot(step_slot_6, s)
                break
        st.exception(e)
        st.stop()


# -------------------------------------------------------------------- Empty state

if st.session_state.phase != "done" or st.session_state.briefing is None:
    st.markdown(
        '<div class="ts-meta" style="margin-top:2rem;">'
        'Fill in the inputs on the left and click <strong>Generate briefing</strong>. '
        'The planner will propose a research plan for your review before agents run.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()


# -------------------------------------------------------------------- Result

briefing_text = st.session_state.briefing
outputs = st.session_state.outputs

stats = st.session_state.get("run_stats") or {}
tot_info_state = st.session_state.get("tot_info") or {}
gallery_images = tot_info_state.get("gallery_images") or []
stats_season = stats.get("season", season)
stats_target = stats.get("target", target)

st.markdown(
    f'<div class="ts-eyebrow">{stats_season}  ·  {stats_target}</div>',
    unsafe_allow_html=True,
)

# Pipeline cards (collapsed) — only after a real run, not for cache/history loads.
if st.session_state.get("pipeline_steps"):
    _render_steps_inline(st.session_state.pipeline_steps)

pdf_filename = f"trend_scout_{stats_season}_{stats_target}.pdf".replace(
    " ", "_"
).replace("'", "")

# Make sure pdf_bytes is ready by the time we render the Download button:
# - Pipeline-runs already filled state.pdf_bytes in Step 6
# - Cache/history-loads come in here without bytes — eager-build once with a
#   spinner so the Download button is always a true single-click download
#   (st.download_button needs the bytes at render time).
expected_pdf_for = (stats_season, stats_target, briefing_text)
if st.session_state.get("pdf_for") != expected_pdf_for:
    try:
        with st.spinner("Preparing PDF …"):
            st.session_state.pdf_bytes = briefing_to_pdf(
                season=stats_season,
                target=stats_target,
                briefing_text=briefing_text,
                outputs=outputs,
                gallery_images=gallery_images,
            )
            st.session_state.pdf_for = expected_pdf_for
    except Exception:
        # PDF build failure shouldn't block the briefing render; the button
        # below will be disabled if bytes aren't there.
        st.session_state.pdf_bytes = None
        st.session_state.pdf_for = expected_pdf_for
pdf_bytes_ready = st.session_state.get("pdf_bytes")

briefing_header_cols = st.columns([2, 1, 1])
with briefing_header_cols[0]:
    st.markdown(
        '<div class="ts-section" style="margin-top:0.5rem;">Briefing</div>',
        unsafe_allow_html=True,
    )
with briefing_header_cols[1]:
    st.write("")
    if st.button("Share", use_container_width=True, key="share_btn"):
        st.session_state.share_dialog_open = True
        st.rerun()
with briefing_header_cols[2]:
    st.write("")
    # Native Streamlit download — works around the iframe-sandbox restriction
    # that blocks <a download> auto-clicks in components.v1.html. Same visual
    # weight as the Share button (both use_container_width).
    st.download_button(
        "PDF export",
        data=pdf_bytes_ready or b"",
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
        key="download_pdf_btn",
        disabled=pdf_bytes_ready is None,
    )


with st.container(border=True):
    render_briefing_card(briefing_text)

render_image_gallery(gallery_images)


# -------------------------------------------------------------------- Share dialog (mail agent + HITL)


@st.dialog("Share via email", width="large")
def share_dialog() -> None:
    """Mail-agent pop-up: collect recipients (email + name + role + language),
    let the LLM draft personalized emails, allow the user to edit each draft,
    then trigger a dummy send action gated behind an explicit approve click."""
    state_briefing = st.session_state.get("briefing") or ""
    state_season = (st.session_state.get("run_stats") or {}).get("season", "")
    state_target = (st.session_state.get("run_stats") or {}).get("target", "")

    if "mail_recipients" not in st.session_state:
        st.session_state.mail_recipients = [{"email": "", "name": "", "role": ""}]
    if "mail_drafts" not in st.session_state:
        st.session_state.mail_drafts = []

    # Stage 1: recipient form
    st.markdown(
        '<div class="ts-eyebrow" style="margin-bottom:0.4rem;">Recipients</div>',
        unsafe_allow_html=True,
    )
    for i, r in enumerate(st.session_state.mail_recipients):
        cols = st.columns([3, 2, 2, 0.5])
        with cols[0]:
            r["email"] = st.text_input(
                "Email", value=r.get("email", ""), key=f"mr_email_{i}",
                placeholder="name@company.com", label_visibility="collapsed",
            )
        with cols[1]:
            r["name"] = st.text_input(
                "Name", value=r.get("name", ""), key=f"mr_name_{i}",
                placeholder="First name", label_visibility="collapsed",
            )
        with cols[2]:
            r["role"] = st.text_input(
                "Role", value=r.get("role", ""), key=f"mr_role_{i}",
                placeholder="Marketing / Buying / …", label_visibility="collapsed",
            )
        with cols[3]:
            if len(st.session_state.mail_recipients) > 1:
                if st.button("✕", key=f"mr_rm_{i}", help="Remove recipient"):
                    st.session_state.mail_recipients.pop(i)
                    st.session_state.mail_drafts = []
                    # Widgets are keyed by row index → after pop, indices
                    # shift and Streamlit's cached values would render the
                    # wrong text in each row. Clear them so the redraw
                    # initializes from the actual recipient list.
                    for k in [
                        k for k in st.session_state
                        if k.startswith(("mr_email_", "mr_name_", "mr_role_"))
                    ]:
                        del st.session_state[k]
                    st.rerun()

    add_col, lang_col = st.columns([1, 2])
    with add_col:
        if st.button("+ Add recipient", key="mr_add", use_container_width=True):
            st.session_state.mail_recipients.append({"email": "", "name": "", "role": ""})
            st.rerun()
    with lang_col:
        language = st.selectbox(
            "Language",
            ["English", "Deutsch", "Français", "Italiano", "Español"],
            index=1,
            key="mr_language",
        )

    # Stage 2: generate
    valid_recipients = [
        r for r in st.session_state.mail_recipients
        if r.get("email", "").strip()
    ]
    invalid_emails = [
        r["email"] for r in valid_recipients
        if not is_valid_email(r["email"])
    ]
    can_generate = bool(valid_recipients) and not invalid_emails
    if invalid_emails:
        st.error(f"Invalid email format: {', '.join(invalid_emails)}")

    st.write("")
    if st.button(
        "Generate emails",
        type="primary",
        disabled=not can_generate,
        use_container_width=True,
        key="mr_generate",
    ):
        try:
            with st.spinner("Mail agent drafting emails ..."):
                drafts = asyncio.run(draft_emails(
                    briefing=state_briefing,
                    season=state_season,
                    target=state_target,
                    language=language,
                    recipients=valid_recipients,
                    brand_profile_block=render_profile_for_prompt(load_profile()),
                    tones_block=render_tones_block(load_tones()),
                ))
            st.session_state.mail_drafts = drafts
            # No explicit rerun — drafts get rendered inline below in the
            # same frame, so the dialog smoothly transitions to the edit
            # view without the close-and-reopen flicker that st.rerun()
            # causes inside @st.dialog.
        except Exception as e:
            st.error(f"Mail agent error: {e}")

    # Stage 3: review + edit
    drafts = st.session_state.mail_drafts or []
    if drafts:
        st.markdown('<hr class="ts-rule"/>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ts-eyebrow" style="margin-bottom:0.5rem;">'
            'Drafts — review and edit before sending</div>',
            unsafe_allow_html=True,
        )
        for i, d in enumerate(drafts):
            with st.container(border=True):
                st.markdown(
                    f'<div class="ts-eyebrow" style="margin:0 0 0.4rem 0;">'
                    f'To: {d.get("email", "")}</div>',
                    unsafe_allow_html=True,
                )
                d["subject"] = st.text_input(
                    "Subject", value=d.get("subject", ""), key=f"md_subj_{i}",
                )
                d["body"] = st.text_area(
                    "Body", value=d.get("body", ""), key=f"md_body_{i}", height=220,
                )

        send_col, cancel_col = st.columns([2, 1])
        with send_col:
            if st.button(
                "Approve and send",
                type="primary",
                use_container_width=True,
                key="mr_send",
            ):
                # Reuse the cached PDF from the result page if it matches the
                # current briefing; otherwise build it on-the-fly so the
                # attachment is always current.
                pdf_for = st.session_state.get("pdf_for")
                expected_pdf_for = (state_season, state_target, state_briefing)
                pdf_bytes = (
                    st.session_state.get("pdf_bytes")
                    if pdf_for == expected_pdf_for else None
                )
                if pdf_bytes is None:
                    try:
                        with st.spinner("Building PDF attachment ..."):
                            pdf_bytes = briefing_to_pdf(
                                season=state_season,
                                target=state_target,
                                briefing_text=state_briefing,
                                outputs=st.session_state.get("outputs") or [],
                                gallery_images=(
                                    st.session_state.get("tot_info") or {}
                                ).get("gallery_images") or [],
                            )
                            st.session_state.pdf_bytes = pdf_bytes
                            st.session_state.pdf_for = expected_pdf_for
                    except Exception as e:
                        st.error(f"PDF build failed: {e}")
                        pdf_bytes = None

                if pdf_bytes is None:
                    return

                pdf_attachment_name = (
                    f"trend_scout_{state_season}_{state_target}.pdf"
                    .replace(" ", "_").replace("'", "")
                )
                try:
                    result = send_smtp_emails(
                        drafts,
                        pdf_bytes=pdf_bytes,
                        pdf_filename=pdf_attachment_name,
                    )
                except Exception as e:
                    st.error(f"SMTP send failed: {e}")
                else:
                    st.session_state.share_dialog_open = False
                    st.session_state.mail_drafts = []
                    attach_note = " (PDF attached)" if result.get("attachment") else ""
                    if result.get("mode") == "smtp":
                        st.toast(
                            f"Sent {result['count']} email(s){attach_note} "
                            f"via {result['note']}",
                            icon="✅",
                        )
                    else:
                        st.toast(
                            f"Drafted {result['count']} email(s){attach_note} — "
                            f"no SMTP configured, nothing was actually sent",
                            icon="⚠️",
                        )
                    st.rerun()
        with cancel_col:
            if st.button("Cancel", use_container_width=True, key="mr_cancel"):
                st.session_state.share_dialog_open = False
                st.session_state.mail_drafts = []
                st.rerun()
    else:
        if st.button("Close", use_container_width=True, key="mr_close"):
            st.session_state.share_dialog_open = False
            st.rerun()


if st.session_state.get("share_dialog_open"):
    share_dialog()


# Tree of Thought — 3 full briefing drafts evaluated, the chosen one is rendered above
tot = st.session_state.get("tot_info") or {}
if tot.get("drafts"):
    drafts = tot["drafts"]
    winner_idx = tot.get("winner_idx", 0)
    reason = tot.get("reason", "")
    angle_names = tot.get("angle_names", [f"Lens {i+1}" for i in range(len(drafts))])
    with st.expander(
        f"Tree of Thought  ·  {len(drafts)} full briefing drafts evaluated"
    ):
        st.markdown(
            f'<div class="ts-meta" style="margin-bottom:0.75rem;">'
            f'<strong>Picker chose Draft {winner_idx + 1}:</strong> '
            f'{angle_names[winner_idx]} lens'
            + (f'<br/><em>Why: {reason}</em>' if reason else "")
            + '</div>',
            unsafe_allow_html=True,
        )
        tab_labels = [
            f"Draft {i + 1}: {name}" + ("  ·  CHOSEN" if i == winner_idx else "")
            for i, name in enumerate(angle_names)
        ]
        tabs = st.tabs(tab_labels)
        for tab, draft_text in zip(tabs, drafts):
            with tab:
                st.markdown(draft_text)


# Agent reports
if outputs:
    total_sources = sum(len(o.get("citations") or []) for o in outputs)
    st.markdown('<div class="ts-section">Research Reports</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ts-meta" style="margin-top:-0.75rem; margin-bottom:1.5rem;">'
        f'{len(outputs)} agents  ·  {total_sources} sources</div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs([o["name"] for o in outputs])
    for tab, o in zip(tabs, outputs):
        with tab:
            evaluation = o.get("evaluation") or {}
            cites = o.get("citations") or []
            text = o.get("text", "")

            if evaluation:
                rounds = evaluation.get("round", 1)
                badge = "approved" if evaluation.get("approved") else "max rounds reached"
                round_label = f"{rounds} round" + ("s" if rounds > 1 else "")
                st.markdown(
                    f'<div class="ts-eval">Evaluator score {evaluation.get("score", 0)}/10  ·  '
                    f'{round_label}  ·  {badge}</div>'
                    f'<div class="ts-eval-feedback">{evaluation.get("feedback", "")}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(text)
            if cites:
                st.markdown(
                    '<div class="ts-eyebrow" style="margin-top:2rem;">Sources</div>',
                    unsafe_allow_html=True,
                )
                render_sources(cites)


# Run stats footer + details expander
if stats:
    st.markdown('<hr class="ts-rule" style="margin-top:4rem;"/>', unsafe_allow_html=True)
    parts = [
        f"Run completed in {stats['elapsed']:.1f}s",
        f"{stats['api_calls']} API calls",
        f"{stats['evaluator_rounds']} evaluator rounds",
        f"{stats['sources']} sources cited",
    ]
    st.markdown(
        f'<div class="ts-meta" style="text-align:center; padding:0.5rem 0 1rem;">'
        + "  ·  ".join(parts) + "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Pipeline details"):
        gallery_stats = tot_info_state.get("gallery_validation") or {}
        candidates = gallery_stats.get("candidates", 0)
        accepted = gallery_stats.get("accepted", 0)
        rejected = max(0, candidates - accepted)

        st.markdown(
            f"**Moodboard validator:** {candidates} candidate og:images collected, "
            f"{accepted} accepted, {rejected} rejected (bot-blocked / off-topic / "
            f"non-fashion)."
        )
        st.markdown(
            f"**Mode:** {stats.get('mode', 'Quality')} (max "
            f"{stats.get('max_rounds', 6)} evaluator rounds per agent)."
        )

        refl = tot_info_state.get("reflection") or {}
        if refl:
            verdict = "revised after critique" if refl.get("revised") else "approved as-is"
            st.markdown(f"**Reflection:** {verdict}.")
            issues = refl.get("issues", "")
            if issues and issues.lower() != "none":
                st.markdown(
                    f'<div class="ts-eval-feedback">{issues}</div>',
                    unsafe_allow_html=True,
                )

        rows: list[str] = ["| Agent | Sources | With og:image | Eval rounds | Score |", "|---|---|---|---|---|"]
        for o in outputs:
            cites = o.get("citations") or []
            with_img = sum(1 for c in cites if c.get("image"))
            ev = o.get("evaluation") or {}
            rows.append(
                f"| {o['name']} | {len(cites)} | {with_img} | "
                f"{ev.get('round', 1)} | {ev.get('score', 0)}/10 |"
            )
        st.markdown("\n".join(rows))
