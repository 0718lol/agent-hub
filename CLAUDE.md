# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AgentHub — IM-style multi-Agent collaboration platform. Users chat with 7+ pre-built AI agents (PM, frontend, backend, tester, devops, designer, builder) plus runtime custom agents. Backend orchestrates LLM streaming and agent-to-agent task assignment over WebSocket; frontend renders chat + a "canvas" panel (DAG, tasks, code preview, deploy log).

Built for the AI Fullstack Competition. xmz's portion focuses on the **eval harness framework** (see `backend/app/harness/` and `backend/app/tools/`) and the **debate sandbox** that intercepts complex queries before normal agent dispatch.

## Commands

```bash
# Backend (FastAPI + WebSocket on :8000)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend (Vite dev server on :3000, proxies /api and /ws → :8000)
cd frontend
npm install
npm run dev

# Eval harness — run judge tools against test suites
cd backend
python -m app.harness.cli list                                   # list suites
python -m app.harness.cli run --suite interaction_judge          # run one
python -m app.harness.cli run --suite all -o report.json --html report.html

# Debate harness smoke test (requires backend running)
cd backend
python test_harness.py
```

No formal test framework — verification is done via `test_harness.py` (WebSocket integration test) and the harness CLI (judge-tool unit tests). No linter configured.

## Architecture

### Request lifecycle (the part that's non-obvious from file names)

User sends a message → frontend WebSocket → `main.py:websocket_endpoint` → routes to one of:

1. **Harness debate intercept** (`routers/harness_handler.py` → `agents/harness_engine.py`) — keyword match or LLM judge decides if the query needs multi-agent debate. If yes, runs Proposer vs Reviewer rounds, sends a debate card to the frontend, and waits for user verdict.
2. **Target agent flow** — single agent reply, with PM optionally assigning downstream agents via `[assign:agent_id]` tags.
3. **Group flow** — PM first, then designer + frontend + backend in parallel (or whoever PM assigned).

**Critical**: generation runs inside `asyncio.create_task` so the WebSocket main loop stays free to receive `stop` messages. Stop signals propagate via `_stop_events: dict[conv_id, asyncio.Event]` checked inside `agent.stream_reply` loops. Awaiting generation in the main loop will silently break the stop button.

### Agent base + prompt engine

`agents/base.py:BaseAgent.stream_reply` is the entry point. It builds messages via `_build_messages` (history from SQLite + inline context + current message, deduped to avoid Anthropic role-alternation violation) and calls `llm_client.chat_stream` with a prompt assembled by `core/prompt_engine.py` (layered: role → task-type-specific addons).

Custom agents are user-created at runtime, persisted in SQLite, loaded into `AGENTS` dict on startup via `_load_custom_agents()`.

### LLM client provider quirks

`core/llm_client.py` is one unified `LLMClient` with provider switch (`openai` / `anthropic` / `claude_code` / `opencode`). The Anthropic path requires **strict user/assistant alternation starting with user** — `_sanitize_for_anthropic` merges consecutive same-role messages and drops leading assistant messages. OpenAI tolerates duplicates; Anthropic 400s. When debugging "consecutive user roles" errors, check `main.py` save-then-fetch sequencing too, not just the sanitizer.

LLM config lives in `backend/data/llm_config.json` (written by `POST /api/settings/llm`). The harness CLI reads the same file.

### Eval harness (xmz's module)

```
backend/app/tools/        — JudgeTool Protocol + 4 implementations
backend/app/harness/      — Runner / Evaluator (4-dim weighted) / Reporter (JSON+HTML) / CLI
backend/app/harness/samples/  — JSON test suites; one per tool
```

Each `JudgeTool` returns a `JudgeResult{decision, score, reason, signals, raw}`. The evaluator scores on 4 weighted dimensions: correctness 40% / confidence 20% / signals 20% / semantic 20%. Adding a new judge = new class in `tools/judge_tools.py` + register in `harness/runner.py:TOOL_REGISTRY` + JSON suite in `harness/samples/`.

Three of the four tools wrap existing logic: `InteractionJudgeTool` → `harness_engine.evaluate_interaction_need`, `QualityJudgeTool` → `auto_evaluator.execute_automated_evaluation`. Don't reimplement; wrap.

### Frontend message protocol

WebSocket messages share `{type, conversation_id, ...}`. Types: `message` (with `stream: bool`), `typing`, `thinking`, `code`, `preview`, `generating`, `task_status`, `read`, `stop`, `harness_debate_result`, `harness_verdict`, `agent_created`, `agent_deleted`, `quality_report`, `deploy_status`.

Streaming messages set `stream: true` and append to the existing streaming bubble for that sender (see `ChatPanel.jsx` WS handler). The first non-streaming chunk closes it.

Backend echoes the user's own message over WS. The frontend filters this with `if (data.sender === 'user') return` to prevent duplicate user bubbles (since `handleSend` already adds locally).

### Inline tag conventions

LLM outputs are parsed for these tags (handled in `main.py` and `MessageBubble.jsx`):

- `[thinking]...[/thinking]` — extracted and broadcast as `thinking` events, stripped from chat
- `[assign:agent_id]` — PM uses this to route to downstream agents; stripped
- `[clarify:q1|q2|...]` — renders a clarification card
- `[options:opt1|opt2|...]` — renders clickable option buttons
- `[mockup:type]` / `[preview:type]` — renders mockup card or triggers canvas preview
- ` ```lang\n...\n``` ` — code blocks are routed to the Canvas panel; chat shows `[code_generated]` placeholder
- Bare HTML (no fence) is detected via regex fallback in `main.py` and also routed to Canvas

### Persistence

SQLite at `backend/data/agenthub.db`. Schema in `core/database.py`. Messages saved with `streaming=False` only after the agent finishes — but the **user message is saved before** fetching history (which is why `base.py:_build_messages` dedups the last entry). LLM error strings (matched on `[LLM Error` / `[LLM 调用出错`) are **not** saved, to avoid feeding them back as context on the next turn.

### What lives outside src

- `xmz/` — xmz's design docs and notes (debate UI plan, harness framework plan, Anthropic API pitfalls)
- `backend/test_harness.py` — encoding-safe WS smoke test for the debate flow
- `backend/harness_report.json` / `harness_full.html` — last harness run outputs
- `资料/` — competition reference materials

## Gotchas

- **Windows GBK terminal** — console output truncates Chinese chars in stack traces. `test_harness.py` does `sys.stdout.reconfigure(encoding='utf-8')`; do the same for any new CLI script.
- **uvicorn `--reload`** can hang on Windows mid-reload (saw it during development). If port 8000 stays in `TIME_WAIT` / zombie state, kill via `powershell -Command "Get-Process python ... Stop-Process -Force"` (using a `.ps1` file — Git Bash mangles `$_` in inline PowerShell).
- **Bash path translation** — Git Bash converts `/F` to `D:/Program Files/Git/F`. Use `cmd //c "..."` or run PowerShell from a file when commands have leading-slash flags.
- **Frontend Vite proxy** is hardcoded to `localhost:8000` in `vite.config.js`. Don't change backend port without updating it.
