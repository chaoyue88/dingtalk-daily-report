# AGENTS.md — dingtalk-daily-report

## Project Overview

Python 3 CLI tool that fetches work-time data from Teambition, formats it as a daily report, and sends it via DingTalk's OAPI. Designed as a Claude/OpenCode local skill triggered by natural language.

## Commands

```bash
# Install dependencies
pip install requests PyJWT

# Configuration management
python scripts/dd_config.py init                          # Create config template
python scripts/dd_config.py verify                        # Validate config + API connectivity
python scripts/dd_config.py templates                     # List DingTalk report templates
python scripts/dd_config.py template-detail TEMPLATE_ID   # Extract field keys from template

# Report generation
python scripts/dd_report.py --preview                     # Preview today's report (stdout only)
python scripts/dd_report.py --send                        # Send today's report to DingTalk
python scripts/dd_report.py --date 2026-03-20 --preview   # Preview for a specific date
python scripts/dd_report.py --user USER_ID --send         # Override Teambition user_id
```

**No build step.** No linter, formatter, type checker, or test framework configured.

## Project Structure

```
scripts/           # Executable CLI scripts (entry points)
  dd_report.py     # Main: fetch worktime → format → send (570 lines)
  dd_config.py     # Config init/verify/template discovery (379 lines)
references/        # Embedded skill resources
  config.default.json   # Default config (always loaded, merged with local override)
  setup-guide.md        # First-time setup instructions
  dingtalk-api.md       # DingTalk OAPI endpoint reference
evals/             # Skill evaluation test cases
SKILL.md           # Skill definition (trigger phrases, workflow, error table)
```

## Code Style

### Language & Runtime

- Python 3, shebang `#!/usr/bin/env python3`
- Dependencies: `requests`, `PyJWT` (graceful import with `sys.exit(1)` on failure)
- No async — synchronous `requests` library for all HTTP calls

### Imports

```python
# 1. Standard library (alphabetical, one per line)
import argparse
import json
import os
from datetime import date, timedelta

# 2. Third-party (try/except for graceful failure)
try:
    import jwt
except ImportError:
    print("缺少依赖: pip install PyJWT")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("缺少依赖: pip install requests")
    sys.exit(1)
```

Local imports inside functions when needed (e.g., `from collections import OrderedDict` at call site).

### Naming

| Element | Convention | Example |
|---|---|---|
| Functions / variables | `snake_case` | `load_config()`, `prev_workday` |
| Private functions | `_leading_underscore` | `_deep_merge()`, `_normalize_project_name()` |
| Private constants | `_SCREAMING_SNAKE` | `_NUM_PREFIX_RE`, `_SCRIPT_DIR` |
| Module-level constants | `SCREAMING_SNAKE` | `CONFIG_DIR`, `CONFIG_TEMPLATE` |
| Files | `snake_case.py` | `dd_report.py`, `dd_config.py` |

### Type Hints

Used on all function signatures. No strict mypy enforcement.

```python
def load_config(local_path: str = None) -> dict:
def prev_workday(d: date) -> date:
def _deep_merge(base: dict, override: dict) -> dict:
def fetch_actual_hours(tb_config: dict, user_id: str, date_str: str) -> list:
```

### Section Organization

Files are divided into sections with Unicode box-drawing comment headers:

```python
# ─── 配置 ────────────────────────────────────────────────────────────────────
# ─── 工作日计算 ───────────────────────────────────────────────────────────────
# ─── Teambition 认证 ──────────────────────────────────────────────────────────
# ─── 格式化日报内容 ──────────────────────────────────────────────────────────
# ─── 钉钉认证与发送 ───────────────────────────────────────────────────────────
# ─── 主流程 ──────────────────────────────────────────────────────────────────
```

### Docstrings & Comments

- Docstrings in Chinese with input/output examples where relevant
- Inline comments in Chinese for non-obvious logic
- Emoji used sparingly in CLI output (⚠️ for warnings, ✅ for success, ❌ for errors)

### Error Handling

```python
# HTTP: always call raise_for_status()
resp.raise_for_status()

# API error codes: check errcode, raise RuntimeError with context
if data.get("errcode") != 0:
    raise RuntimeError(f"获取钉钉 token 失败: {data.get('errmsg')}")

# Graceful degradation: silent pass for non-critical lookups (e.g., project name cache)
try:
    ...  # optional API enrichment
except Exception:
    pass

# Fatal errors: print message + sys.exit(1)
if not user_id:
    print("错误: 未指定用户 ID...")
    sys.exit(1)
```

### Configuration Layer

Two-layer merge (defaults → local override):

1. `references/config.default.json` — embedded, always loaded
2. `~/.dingtalk-daily/config.json` — user override, only override fields needed

Merge via `_deep_merge()` (recursive dict merge, override wins). Missing credentials trigger setup guidance rather than crashes.

### File I/O

- Always specify `encoding="utf-8"` for file operations
- JSON: `json.dump()` with `indent=2, ensure_ascii=False` for Chinese content
- Config files use restrictive permissions (`os.chmod(path, 0o600)`)

### API Patterns

- **DingTalk**: OAPI (`oapi.dingtalk.com`), access_token via query param, token cached to `~/.dingtalk-daily/.token_cache.json`
- **Teambition**: Open API (`open.teambition.com`), JWT auth regenerated per request (no caching)
- All HTTP calls use explicit `timeout=` parameter
- Markdown content sent to DingTalk requires `&` → `&amp;` escaping

### CLI Patterns

- `argparse` with `ArgumentParser(description="...")`
- `action="store_true"` for boolean flags (`--send`, `--preview`, `--force`)
- Optional positional args via `add_argument()` (e.g., `template_id`)
- Subcommands via `add_subparsers(dest="cmd")` in `dd_config.py`

## Key Constraints

- Never suppress type errors or use bare `except: pass` in critical paths (cache lookups are the exception)
- Never commit credential files or token caches (`.gitignore` excludes `__pycache__/`, `.token_cache.json`)
- All user-facing messages in Chinese; code identifiers in English
- No external config framework — pure stdlib `json` + `argparse`
