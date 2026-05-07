# Trend Scout

Multi-Agent Trend-Briefing-Generator. Streamlit + Gemini.

## Was es macht

User gibt Saison + Zielgruppe ein. Pipeline:

1. **Planner** schlägt einen Recherche-Plan vor (pro Agent 2-3 Angles + cross-cutting Themen)
2. **HITL Gate** — User reviewt den Plan, editiert Angles, fügt Custom-Agents hinzu, freigibt
3. **N parallele Research-Agenten** mit `google_search` + text-only Evaluator-Optimizer-Loop pro Agent
4. **Tree-of-Thought Synthesis** — 3 Briefing-Drafts unter verschiedenen Linsen (Commercial, Strategic, Signal-Strength), Picker wählt den stärksten
5. **Reflection** — Critic-LLM liest den gewählten Draft; bei Issues läuft eine Revisions-Runde
6. **Multimodaler Moodboard-Validator** — sammelt og:images aus den Citations (Cap 30), lässt Gemini multimodal prüfen, filtert Müll, finaler Cap 20
7. **Render** — Briefing-Card (Executive Summary, Key Themes, Recommended Colors mit Hex+Bild, Risk Assessment) + Moodboard + Research-Reports + ToT-Expander + Pipeline-Details

## Komfort-Features

- **Mode-Toggle** im Sidebar: Fast (max 2 Eval-Rounds) vs. Quality (max 6)
- **Caching**: gleiche Saison/Target/Plan-Konfig → wird aus Disk-History geladen, kein API-Call
- **History**: letzte Briefings im Sidebar, klickbar zum Reload
- **Export**: Markdown (Plain-Text) oder HTML mit eingebetteten Bild-URLs (Browser → Print → Save as PDF)

## Stack

- **Gemini 2.5 Flash** mit nativem `google_search`-Grounding
- **`asyncio.gather`** für parallele Agents und parallele HTTP-Stages
- **Streamlit** für UI mit Live-Progress
- **httpx** für og:image- und og:title-Scraping aus den zitierten Quellen

Ein API-Key (`GEMINI_API_KEY`), kostenlos via https://aistudio.google.com/apikey. Briefing-History persistiert lokal unter `~/.trend-scout/history/`.

## Repo-Layout

```
streamlit_app.py            # UI shell: Sidebar, Phasen idle/planned/done, Final-Render
trend_scout/
  __init__.py
  config.py                 # AGENTS dict, Gallery-Caps, MAX_AGENT_ROUNDS
  prompts.py                # alle System-Prompts (Planner, Researcher, Evaluator, Synthesis, Picker, Validator, Reflection-Critic, Reflection-Reviser)
  llm.py                    # Gemini-Client (per-Loop Cache) + Citation-Enrichment + Image-Bytes-Fetch
  research.py               # Planner + per-Agent Loop (research → eval → revise)
  synthesis.py              # ToT-Drafts + Picker + Reflection + Moodboard-Validator + Color-Mapping
  storage.py                # JSON-History + Hash-basiertes Caching (~/.trend-scout/history/)
  export.py                 # HTML-Export (Browser → Print → Save as PDF)
  ui.py                     # CSS + Briefing-Renderer + Moodboard-Galerie + Color-Cards
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# .env öffnen, GEMINI_API_KEY eintragen
```

## Starten

```powershell
streamlit run streamlit_app.py
```

Pro Run: typisch ~30-60s. Free Tier reicht für mehrere Demos pro Tag.
