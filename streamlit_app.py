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


# Sidebar-Hints — pure UI strings, kept here so config.py stays domain-only.
AGENT_SIDEBAR_HINTS: dict[str, str] = {
    "Runway": "catwalks, editorials",
    "Social": "TikTok, Pinterest, Instagram",
    "Color": "Pantone, WGSN, forecasts",
    "Competitor": "Closed, Marc O'Polo",
}
from trend_scout.export import briefing_to_html
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
                label = f"{rec['season']} · {rec['target']}"
                cols = st.columns([4, 1])
                with cols[0]:
                    if st.button(
                        f"{label}\n\n{ts}",
                        key=f"hist_load_{rec['id']}",
                        use_container_width=True,
                    ):
                        st.session_state.pending_history_load = rec["id"]
                        st.rerun()
                with cols[1]:
                    if st.button("✕", key=f"hist_del_{rec['id']}", help="Delete"):
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

st.markdown('<div class="ts-eyebrow">DRYKORN · Trend Briefing</div>', unsafe_allow_html=True)
st.markdown('<h1>Trend Scout</h1>', unsafe_allow_html=True)
st.markdown(
    '<div class="ts-meta">Planner → HITL gate → N parallel researchers '
    '(google_search + text-only evaluator-optimizer loop) → ToT synthesis '
    '→ multimodal moodboard validator → reflection</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="ts-rule"/>', unsafe_allow_html=True)


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
    # Custom-Agents bleiben erhalten — User kann sie via "Remove"-Button selbst rauswerfen.
    # Wir resetten nur die Plan-Text-Cache-Keys der Default-Agents damit der Planner-
    # Output frisch eingefüllt wird.
    for _agent in AGENTS:
        st.session_state.pop(f"plan_text_{_agent}", None)
        st.session_state.pop(f"plan_inc_{_agent}", None)

    try:
        with st.spinner("Planner agent decomposing the request ..."):
            plan = asyncio.run(run_planner(season, target))
        st.session_state.plan = plan
        st.session_state.phase = "planned"
    except Exception as e:
        st.error(f"Planner error: {e}")
        st.exception(e)
        st.stop()


# -------------------------------------------------------------------- HITL plan review

if st.session_state.phase == "planned":
    plan = st.session_state.plan or {}
    st.markdown('<div class="ts-section">Plan Review</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ts-meta" style="margin-top:-0.5rem; margin-bottom:1.5rem;">'
        'Edit the research angles per agent or untick a domain to skip it. '
        'Cross-cutting themes are passed to the synthesis as additional context.'
        '</div>',
        unsafe_allow_html=True,
    )

    edited_plan: dict[str, list[str]] = {}
    enabled_agents: set[str] = set()
    for agent_name in AGENTS.keys():
        text_key = f"plan_text_{agent_name}"
        if text_key not in st.session_state:
            st.session_state[text_key] = "\n".join(
                f"- {q}" for q in plan.get(agent_name, [])
            )

        with st.container(border=True):
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
                height=110,
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

    custom_agent_specs: list[tuple[str, str, list[str] | None]] = []
    if st.session_state.custom_agents:
        st.markdown(
            '<div class="ts-eyebrow" style="margin-top:2rem;">Custom agents (user-added)</div>',
            unsafe_allow_html=True,
        )
    for ca in st.session_state.custom_agents:
        cid = ca["id"]
        with st.container(border=True):
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

    st.button(
        "+ Add custom agent",
        on_click=add_custom_agent,
        help="Add an extra research domain on the fly (e.g. Sustainability, Material Innovation, Regional Market)",
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
        f"Approve & run research with {n_enabled} agent{'s' if n_enabled != 1 else ''}",
        type="primary",
        disabled=n_enabled == 0,
    )

    if approve_btn:
        st.session_state.plan = edited_plan
        st.session_state.enabled_agents = list(enabled_agents)

        agent_specs: list[tuple[str, str, list[str] | None]] = []
        for agent_name, system_prompt in AGENTS.items():
            if agent_name in enabled_agents:
                queries = edited_plan.get(agent_name) or None
                agent_specs.append((agent_name, system_prompt, queries))
        agent_specs.extend(custom_agent_specs)

        states: dict[str, tuple[str, float | None]] = {
            spec[0]: ("running", None) for spec in agent_specs
        }
        icon = {"running": "[ .. ]", "done": "[ OK ]", "pending": "[ -- ]"}

        status = st.status("Agents researching in parallel ...", expanded=True)
        progress_slot = status.empty()
        eval_scores: dict[str, dict] = {}

        def render() -> None:
            lines = []
            for n, (st_name, dt) in states.items():
                extra = f"  ·  {dt:.1f}s" if dt is not None else ""
                ev = eval_scores.get(n)
                if ev is not None:
                    rounds = ev.get("round", 1)
                    badge = "OK" if ev["approved"] else "REVISED"
                    extra += (
                        f"  ·  score {ev['score']}/10 ({badge}, {rounds} round"
                        f"{'s' if rounds > 1 else ''})"
                    )
                lines.append(f"`{icon[st_name]}`  **{n}**{extra}")
            lines.append("")
            all_done = all(s == "done" for s, _ in states.values())
            synth_icon = icon["running"] if all_done else icon["pending"]
            lines.append(f"`{synth_icon}`  **Synthesis**")
            progress_slot.markdown("\n\n".join(lines))

        render()

        def on_agent_done(name: str, elapsed: float, evaluation: dict) -> None:
            states[name] = ("done", elapsed)
            eval_scores[name] = evaluation
            render()

        max_rounds = 2 if mode == "Fast" else 6
        input_hash = compute_input_hash(season, target, agent_specs)

        # Cache-Hit: serve the most recent matching run, no API call.
        if use_cache:
            cached = find_cached(input_hash)
            if cached is not None:
                st.session_state.briefing = cached.get("briefing")
                st.session_state.outputs = cached.get("outputs", [])
                st.session_state.tot_info = cached.get("tot_info")
                st.session_state.run_stats = cached.get("run_stats")
                st.session_state.phase = "done"
                status.update(label="Loaded from cache.", state="complete")
                st.rerun()

        try:
            briefing, outputs, tot_info = asyncio.run(
                run_briefing(
                    season,
                    target,
                    on_agent_done,
                    agent_specs,
                    cross_cutting=plan.get("CrossCutting", []),
                    max_rounds=max_rounds,
                )
            )
            elapsed = time.perf_counter() - st.session_state.run_t0

            rounds_total = sum(o["evaluation"].get("round", 1) for o in outputs)
            sources_total = sum(len(o.get("citations") or []) for o in outputs)
            # API calls per agent per round: researcher + evaluator = 2.
            # Plus 1 planner + 3 ToT drafts + 1 picker + 1 reflection + 1 validator
            # + 0-1 revision pass.
            revised = bool((tot_info.get("reflection") or {}).get("revised"))
            api_calls = 1 + rounds_total * 2 + 3 + 1 + 1 + 1 + (1 if revised else 0)

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
                "enabled_count": len(enabled_agents),
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
                    enabled_agents=list(enabled_agents),
                    input_hash=input_hash,
                )
            except Exception:
                pass  # history is best-effort, don't break the UI on disk errors

            status.update(label="Briefing ready.", state="complete")
            st.rerun()
        except Exception as e:
            status.update(label=f"Error: {e}", state="error")
            st.exception(e)
            st.stop()
    else:
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

briefing_header_cols = st.columns([5, 1])
with briefing_header_cols[0]:
    st.markdown(
        '<div class="ts-section" style="margin-top:0.5rem;">Briefing</div>',
        unsafe_allow_html=True,
    )
with briefing_header_cols[1]:
    st.write("")
    download_filename = f"trend_scout_{stats_season}_{stats_target}.md".replace(
        " ", "_"
    ).replace("'", "")
    saved_plan = st.session_state.get("plan") or {}
    enabled_agent_names = st.session_state.get("enabled_agents") or list(AGENTS.keys())
    plan_section = ""
    if saved_plan:
        plan_section = "## Research plan (planner output, user-approved)\n\n"
        for agent_name in AGENTS.keys():
            queries = saved_plan.get(agent_name, []) or []
            if agent_name not in enabled_agent_names:
                plan_section += f"### {agent_name}\n_(skipped by user)_\n\n"
                continue
            if not queries:
                plan_section += f"### {agent_name}\n_(no specific angles given)_\n\n"
                continue
            plan_section += f"### {agent_name}\n"
            for q in queries:
                plan_section += f"- {q}\n"
            plan_section += "\n"
        default_names = set(AGENTS.keys())
        custom_in_plan = [
            n for n in enabled_agent_names
            if n not in default_names and n != "CrossCutting"
        ]
        for agent_name in custom_in_plan:
            queries = saved_plan.get(agent_name, []) or []
            plan_section += f"### {agent_name} _(custom)_\n"
            if queries:
                for q in queries:
                    plan_section += f"- {q}\n"
            else:
                plan_section += "_(no specific angles given)_\n"
            plan_section += "\n"
        cross = saved_plan.get("CrossCutting") or []
        if cross:
            plan_section += "**Cross-cutting themes**\n"
            for theme in cross:
                plan_section += f"- {theme}\n"
            plan_section += "\n"
        plan_section += "---\n\n"
    download_md = (
        f"# Trend Scout briefing\n\n"
        f"Season: {stats_season}\n"
        f"Target group: {stats_target}\n\n"
        "---\n\n"
        + plan_section
        + briefing_text
        + "\n"
    )
    st.download_button(
        "Download .md",
        data=download_md,
        file_name=download_filename,
        mime="text/markdown",
        use_container_width=True,
    )

    download_html = briefing_to_html(
        season=stats_season,
        target=stats_target,
        briefing_text=briefing_text,
        outputs=outputs,
        gallery_images=gallery_images,
    )
    download_html_filename = download_filename.replace(".md", ".html")
    st.download_button(
        "Download .html (print to PDF)",
        data=download_html,
        file_name=download_html_filename,
        mime="text/html",
        use_container_width=True,
        help="Open in a browser, then File → Print → Save as PDF for a "
        "printable version with the moodboard images embedded.",
    )

with st.container(border=True):
    render_briefing_card(briefing_text)

render_image_gallery(gallery_images)


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
