# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This is a long-form Chinese web novel generation system that solves the core challenge of **narrative coherence at 100k+ word scale**. It's not a toy that calls an LLM once—it's a production pipeline that manages layered memory, consistency checking, and narrative pacing across hundreds of chapters.

The system addresses three fundamental problems:
1. **Length**: Web novels exceed any context window; requires hierarchical memory + retrieval
2. **Coherence**: Character states, power systems, and plot threads must stay consistent; requires structured state tracking + validation
3. **Pacing**: Reader retention depends on hooks and payoff rhythm; requires a deterministic pacing engine

## Architecture: Three-Layer Memory System

This is the **foundation** of the entire system. Understanding it is critical:

### Short-term Memory (工作记忆)
- **What**: Full text of the most recent 2-5 chapters
- **How**: Direct file read from `chapters/ch*.md`
- **Purpose**: Adjacent chapter continuity

### Mid-term Memory (情节记忆)
- **What**: Rolling chapter summaries + world state snapshot (protagonist tier/location, alive/dead characters, open plot threads)
- **How**: `summaries/chapters.json` + `state.json` (structured, not embeddings)
- **Purpose**: Global narrative state without reading the entire book

### Long-term Memory (世界记忆)
- **What**: Semantic vector retrieval of historical passages
- **How**: `vectors.npy` + `vectors_meta.json` (numpy cosine similarity, DashScope text-embedding-v3)
- **Purpose**: Recall relevant past details when writing new chapters

## Core Writing Loop (engine.py)

The `write_one_chapter()` function in `engine.py` is the **heart of the system**. Both CLI and Web share this single implementation. The flow:

```
1. Pacing (compute_beat) → deterministic beat classification
2. Vector recall → semantic retrieval of relevant history
3. Write → chapter_writer with full context injection
4. Consolidate → extract summary + update world state
5. Review → consistency checking (rules + LLM)
6. Rewrite loop → if errors found and rewrites remain
7. Save + Index → persist chapter + index to vector store
```

**Critical**: If final draft still has errors, text is saved but **world state is NOT updated** (keeps clean state from previous chapter). This prevents corrupted state from propagating.

## Progress Reporting Abstraction (reporting.py)

The system supports **two frontends** (CLI + Web) without duplicating business logic:

- `ConsoleReporter`: prints to terminal with rich formatting (used by CLI)
- `QueueReporter`: pushes events to a queue for SSE streaming (used by Web)

All orchestration code (engine, ideation, outline generation) takes a `Reporter` parameter. This decouples "what happened" from "how to display it."

## Project Structure (books/)

Each book is a **self-contained directory** under `books/<slug>/`:

```
bible.json              # World rules, power system, golden finger
characters.json         # Character registry
outline.json            # Hierarchical outline (volumes → chapters)
state.json              # World state snapshot (mid-term memory)
summaries/chapters.json # Rolling chapter summaries (mid-term memory)
reviews.json            # Consistency check reports per chapter
vectors.npy             # Vector store matrix (long-term memory)
vectors_meta.json       # Vector metadata (chapter mapping)
chapters/ch0001.md      # Full chapter text
```

**Key invariant**: All JSON files use `storage._to_plain()` for serialization, which recursively converts dataclasses to dicts. Use `from_dict()` class methods when deserializing.

## Web API (server/)

FastAPI backend wraps the CLI logic:
- **Read endpoints**: GET /api/books/{slug}/{resource}
- **Edit endpoints**: PUT for bible/characters/outline/chapters (saves back to JSON)
- **Task endpoints**: POST for long-running operations (init/outline/write/run/reindex)
- **SSE progress**: GET /api/tasks/{task_id}/events (streams QueueReporter events)

**Per-book write lock**: TaskManager enforces only one write task per book at a time (they share `state.json`).

## Development Commands

### Running the CLI
```bash
# Install in development mode
.venv/bin/pip install -e .

# Test a command
.venv/bin/novel --help
.venv/bin/novel ping  # Test Codex connectivity

# Full workflow example
novel init -i "创意" -g 玄幻 -t 书名
novel outline --book 书名 --volumes 3 --chapters 8
novel write --book 书名 -c 1
novel run --book 书名 -n 5  # Batch write 5 chapters
```

### Running the Web Interface
```bash
# Backend (API + task manager)
.venv/bin/novel serve  # Starts on :8000

# Frontend development (separate terminal)
cd web
npm install
npm run dev  # Vite dev server on :5173, proxies /api to :8000

# Production build
cd web && npm run build  # Outputs to web/dist/
novel serve  # Serves both API + static frontend
```

### Testing individual components
```bash
# Test a module import
.venv/bin/python -c "from novel_agent.engine import write_one_chapter; print('OK')"

# Test FastAPI routes
.venv/bin/python -c "
from fastapi.testclient import TestClient
from novel_agent.server import create_app
c = TestClient(create_app())
print(c.get('/api/books').json())
"

# Test TypeScript compilation
cd web && node_modules/.bin/tsc -b
```

## Configuration (.env)

Two keys control different capabilities:

- `ANTHROPIC_API_KEY`: Required. Powers all generation (writing, outlining, extraction, review)
- `DASHSCOPE_API_KEY`: Optional. Powers vector recall via text-embedding-v3
  - If missing, vector recall **silently degrades** (system continues without it)
  - Set `EMBED_BASE_URL`/`EMBED_MODEL`/`EMBED_DIM` to customize

**Model selection**:
- Writing: Opus (quality over cost)
- Extraction/review: Sonnet (cheaper, still accurate)
- Embeddings: DashScope text-embedding-v3 (1024-dim)

## Key Constraints and Design Decisions

1. **Pacing is deterministic**: `pacing.py` uses no LLM calls. It classifies chapters based on position in volume, marked cool points, and distance since last payoff. This is intentional—pacing structure should be architectural, not random.

2. **Vector store is pure numpy**: Uses cosine similarity with no external dependencies (sqlite-vec was avoided due to Python 3.14 C extension stability). Filtering is done in-memory (`before_chapter`, `exclude_recent`).

3. **Consistency checks happen AFTER extraction**: The flow is always `write → extract → check → commit`. If checks fail, extraction is discarded. This prevents bad state from entering memory.

4. **No parallel writes per book**: `TaskManager` uses per-slug locks. Multiple chapters of the same book cannot be written concurrently (they share mutable `state.json`).

5. **Reporter abstraction enables dual frontends**: All progress must go through `Reporter.step()/info()/warn()/error()/done()`. Never print directly—this breaks the Web frontend's SSE stream.

## Common Patterns

### Adding a new generation step
1. Accept a `Reporter` parameter
2. Call `rep.step("Starting X")` before long operations
3. Call `rep.info("detail")` for incremental progress
4. Call `rep.warn()` for non-fatal issues, `rep.error()` for failures
5. Return structured data (dict or dataclass)

### Adding a new API endpoint
1. Define Pydantic models for request bodies in `server/app.py`
2. For long tasks: create task via `tasks.start()`, return `task_id`
3. The task's `work` function receives a `QueueReporter`—use it for progress
4. Frontend subscribes to `/api/tasks/{task_id}/events` for SSE stream

### Modifying world state schema
1. Update `memory/state_models.py` dataclass
2. Update `from_dict()` method with backward-compatible defaults
3. Regenerate any books' `state.json` with new schema (or they'll use defaults)

## Frontend (web/)

Vite + React + TypeScript SPA with React Query for server state:

- `src/api.ts`: Typed API client
- `src/useTaskStream.ts`: SSE hook for progress streaming
- `src/pages/Workspace.tsx`: Main book workspace (tabs: overview/bible/characters/outline/chapters/reviews)
- `src/components/ProgressDrawer.tsx`: Real-time progress panel for long tasks

Vite proxies `/api` to backend during development. In production, FastAPI serves the built static files via `StaticFiles`.

## Known Limitations

- Vector recall and batch writing tested mainly offline (not extensively with real DashScope key + multi-chapter production runs)
- No automated test suite (validation is manual)
- Outline generation is one-shot (adding volumes mid-writing requires manual JSON editing)
- World state is snapshot-based, not a temporal event-sourced graph (the original plan included an event-sourced knowledge graph, but current implementation uses a simpler state snapshot model)
