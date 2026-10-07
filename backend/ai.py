"""
AI integration for the Explainable Compiler.

Two features live here:
  1. `ask_question(...)`   — a Q&A assistant that can answer general compiler-theory
     questions, and, when given the current program + pipeline output as context,
     answer questions specific to what the user is looking at.
  2. `generate_report(...)` — turns one full pipeline result into a single
     human-readable, phase-by-phase explanation of that specific program's
     compilation, written for someone learning the material.

Design notes:
  - The Anthropic API key is read server-side from the ANTHROPIC_API_KEY
    environment variable. It is never sent to, or read from, the browser —
    the frontend only ever talks to *this* backend's /api/ask and
    /api/report endpoints.
  - If no key is configured, both functions raise AIError with a message the
    UI displays inline, instead of the server crashing on startup.
"""
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import httpx
except ImportError:
    httpx = None

try:
    import anthropic
except ImportError:  # pragma: no cover - the package is in requirements.txt
    anthropic = None

DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
MAX_QUESTION_LENGTH = 2000

_SYSTEM_PROMPT = """You are the built-in AI assistant of "Explainable Compiler", a teaching tool \
that visualizes every phase of compiling a small shared subset of C / C++ / Java / Python \
(variable declarations, arithmetic, comparisons, if/else, while, print, basic input). It shows: \
tokens, an AST with per-expression syntax trees + postfix form, a symbol table, intermediate code \
(three-address code, quadruples, triples, indirect triples, and industry-standard LLVM IR in SSA form), \
optimizations, simplified target instructions, and execution output.

Answer questions about compiler theory in general (lexical analysis, parsing, grammars, \
intermediate representations, LLVM IR, SSA form, optimization passes, code generation, etc.) clearly \
and concisely, the way a good TA would. When the user's message includes a CONTEXT block with their current \
program and/or its analysis, ground your answer in that specific code and data rather than \
speaking only in the abstract — reference their actual variable names, instructions, or numbers \
where it helps. If a question is about a construct this tool doesn't support (e.g. functions, \
arrays, classes), say so plainly and explain how it would generally work in a real compiler.

Keep answers focused: a few short paragraphs or a short list is usually enough. Use plain text \
with occasional `code formatting`, not headers, unless the question truly needs structure."""

_REPORT_SYSTEM_PROMPT = """You are the built-in AI assistant of "Explainable Compiler", a teaching \
tool that visualizes every phase of compiling a small shared subset of C / C++ / Java / Python. \
You will be given one program's complete phase-by-phase pipeline output as JSON. Write a single \
well-organized Markdown report that walks a learner through exactly what happened to *this* \
program, phase by phase, in your own words — don't just restate the JSON. For each phase, explain \
briefly what the phase's job is in general, then describe what actually happened for this program, \
citing concrete details (actual token values, the actual AST shape, the actual TAC/quadruples/ \
triples/indirect-triples and LLVM IR, which optimizations fired and why, what the target code does, \
and the actual output). End with a short "Key Takeaways" section connecting the dots. Use Markdown \
headings (##) per phase, and keep the whole report focused — a few paragraphs or a short list per \
phase, not a wall of text. If a phase has an error or was skipped, say so and explain why the \
pipeline stopped there instead of describing later phases."""


class AIError(Exception):
    """Raised for any AI-feature failure; message is safe to show in the UI."""


def _get_nvidia_key() -> str | None:
    return os.environ.get("NVIDIA_API_KEY") or os.environ.get("NEMOTRON_API_KEY")


def _get_nvidia_model() -> str:
    return os.environ.get("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL)


def _get_claude_model() -> str:
    return os.environ.get("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)


def get_provider() -> str | None:
    if _get_nvidia_key():
        return f"NVIDIA Nemotron ({_get_nvidia_model()})"
    if os.environ.get("ANTHROPIC_API_KEY") and anthropic is not None:
        return f"Anthropic ({_get_claude_model()})"
    return None


def is_configured() -> bool:
    return get_provider() is not None


def _call_nvidia(system_prompt: str, user_content: str, max_tokens: int) -> str:
    if httpx is None:
        raise AIError("The 'httpx' package is required for NVIDIA API calls.")
    api_key = _get_nvidia_key()
    if not api_key:
        raise AIError("NVIDIA_API_KEY environment variable is not set.")
    url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _get_nvidia_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("error", {}).get("message", resp.text) or resp.text
                except Exception:
                    pass
                raise AIError(f"NVIDIA API error ({resp.status_code}): {err_text}")
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return "(The assistant returned an empty response — please try again.)"
            text = choices[0].get("message", {}).get("content", "")
            return text.strip() or "(The assistant returned an empty response — please try again.)"
    except httpx.RequestError as e:
        raise AIError(f"Network error contacting NVIDIA API: {e}") from e


def _call_anthropic(system_prompt: str, user_content: str, max_tokens: int) -> str:
    if anthropic is None:
        raise AIError("The 'anthropic' package is not installed on the server.")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AIError(
            "AI features aren't configured yet — set ANTHROPIC_API_KEY or NVIDIA_API_KEY "
            "environment variable on the server."
        )
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=_get_claude_model(),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:  # noqa: BLE001
        raise AIError(f"Anthropic API request failed: {e}") from e

    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    return text.strip() or "(The assistant returned an empty response — please try again.)"


def _condense_phases(phases: dict) -> dict:
    """Trims large/repetitive fields so the report prompt stays a reasonable size
    (e.g. full token lists can be long for bigger programs)."""
    trimmed = json.loads(json.dumps(phases))  # cheap deep copy
    lex = trimmed.get("lexical")
    if isinstance(lex, dict) and isinstance(lex.get("tokens"), list) and len(lex["tokens"]) > 80:
        lex["tokens"] = lex["tokens"][:80] + [{"note": "...truncated for length..."}]
    return trimmed


def ask_question(question: str, context: dict | None = None) -> str:
    question = (question or "").strip()
    if not question:
        raise AIError("Please type a question first.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise AIError(f"Question is too long (max {MAX_QUESTION_LENGTH} characters).")

    user_content = question
    if context and context.get("code"):
        ctx_json = json.dumps(_condense_phases(context.get("phases") or {}))[:12000]
        user_content = (
            f"CONTEXT\nLanguage: {context.get('language', 'unknown')}\n"
            f"Source code:\n```\n{context.get('code', '')[:4000]}\n```\n"
            f"Current tab open in the UI: {context.get('activePhase', 'n/a')}\n"
            f"Pipeline analysis so far (JSON, may be partial/truncated): {ctx_json}\n\n"
            f"QUESTION\n{question}"
        )

    if _get_nvidia_key():
        return _call_nvidia(_SYSTEM_PROMPT, user_content, max_tokens=900)
    elif os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic(_SYSTEM_PROMPT, user_content, max_tokens=900)
    else:
        raise AIError(
            "AI features aren't configured yet — set NVIDIA_API_KEY (for Nemotron) "
            "or ANTHROPIC_API_KEY in your environment and restart the server."
        )


def generate_report(language: str, code: str, phases: dict) -> str:
    if not phases:
        raise AIError("Nothing to report on yet — run Analyze first.")

    condensed = _condense_phases(phases)
    user_content = (
        f"Language: {language}\n"
        f"Source code:\n```\n{code[:6000]}\n```\n\n"
        f"Full pipeline JSON:\n{json.dumps(condensed)[:18000]}"
    )

    if _get_nvidia_key():
        return _call_nvidia(_REPORT_SYSTEM_PROMPT, user_content, max_tokens=3000)
    elif os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic(_REPORT_SYSTEM_PROMPT, user_content, max_tokens=3000)
    else:
        raise AIError(
            "AI features aren't configured yet — set NVIDIA_API_KEY (for Nemotron) "
            "or ANTHROPIC_API_KEY in your environment and restart the server."
        )
