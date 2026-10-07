# Explainable Compiler

A visual, interactive compiler-phase analyzer for **C, C++, Java, and Python** — built to show
students what actually happens inside a compiler/interpreter, phase by phase, rather than just
running their code.

This is a real frontend/backend application:

- **`backend/`** — a FastAPI service that does the actual work: tokenizing, parsing, semantic
  checking, three-address-code generation (plus quadruples, triples, and indirect triples),
  expression-tree/postfix extraction, optimization, target-code generation, execution (via a
  small built-in interpreter), and an optional AI assistant. Nothing about the compiler pipeline
  itself is faked or hardcoded per example.
- **`frontend/`** — a static HTML/CSS/JS single-page app that calls the backend's REST API and
  renders every phase: token tables, clickable expression syntax trees with postfix and a
  step-by-step stack evaluation, the symbol table with a memory-box view, three-address
  code alongside quadruples/triples/indirect triples, before/after optimization bar charts and
  diffs with plain-language explanations, a target-code view, a file-upload option for the code
  editor, a floating AI chat assistant, and an on-demand AI-written compilation report.

## Folder structure

```
explainable-compiler/
├── README.md
├── backend/
│   ├── main.py                 # FastAPI app: REST API + serves the frontend
│   ├── requirements.txt
│   ├── compiler/
│   │   ├── lexer.py            # preprocessing + tokenizer
│   │   ├── parser_.py          # recursive-descent parser -> AST (brace-style + Python indent-style)
│   │   ├── semantic.py         # semantic checks + symbol table construction
│   │   ├── ir.py                # three-address-code generation
│   │   ├── optimizer.py        # constant folding/propagation, algebraic simplification, CSE, dead code elim.
│   │   ├── target.py           # educational target-code (pseudo-assembly) generation
│   │   ├── executor.py         # tree-walking interpreter used to actually run the program
│   │   └── pipeline.py         # orchestrates all phases into one API response
│   ├── ai.py                    # AI assistant: Q&A + AI-written compilation reports (Anthropic API)
│   └── languages/
│       └── config.py            # per-language keywords, sample code, pipeline order
└── frontend/
    ├── index.html                # also holds the floating AI chat panel markup
    ├── style.css
    └── app.js                   # UI rendering, AST tree drawing, file upload, AI panel, calls the backend API
```

## What's implemented vs. what isn't (read this first)

This analyzes a shared subset of constructs common to all four languages, so the pipeline is
genuinely comparable:

- Variable declarations & assignment (`int a = 10;` / `a = 10`)
- Arithmetic: `+ - * /` with correct precedence and parentheses
- Comparisons: `== != < > <= >=`
- `if` / `else`, `while` loops
- `print` / `printf` / `cout <<` / `System.out.println` (language-specific surface syntax)
- Basic `input()` / `scanf` reading from a stdin box

**Not implemented:** functions/methods, arrays, classes/objects beyond boilerplate stripping,
`for` loops, string methods, or standard libraries. Code using those will produce an honest,
located syntax error — the analyzer never silently guesses.

Target code is a **simplified instruction-style representation** (`LOAD`/`STORE`/`ADD`-style
pseudo-assembly), explicitly labeled as such — never claimed to be real machine code, JVM
bytecode, or CPython bytecode.

**Intermediate representations.** Every program is shown in five forms: four textbook formats
plus industry-standard LLVM IR:
- **Three-Address Code (TAC)** — readable `res = a1 op a2`-style instructions.
- **Quadruples** — a table with an explicit `(op, arg1, arg2, result)` row per instruction.
- **Triples** — `(op, arg1, arg2)` with no result column; operands that come from an earlier
  instruction are written as `(i)`, referring to that instruction's position instead of a temp name.
- **Indirect Triples** — a pointer list on top of the triple table, so a later optimization pass
  could reorder execution by editing pointers instead of moving triples.
- **LLVM IR (SSA Form)** — strongly-typed, infinite-register intermediate code (`.ll` module)
  matching the Clang `-O0` stack allocation model (`alloca`, `load`, `store`, `icmp`, `br`, `@printf`),
  complete with a breakdown of key LLVM concepts (SSA form, explicit typing, basic blocks).

**Expression trees & postfix.** Every compound expression found anywhere in the program (variable
initializers, assignment right-hand sides, `if`/`while` conditions, print arguments) gets its own
clickable syntax-tree visualization, its postfix (Reverse Polish) form, and a step-by-step
stack-based evaluation trace showing how that postfix form would be evaluated.

**Security note:** execution runs a hand-written Python tree-walking interpreter over the parsed
AST — it never calls `eval()`, shells out to a compiler, or touches the filesystem/network, so no
container/OS-level sandbox is required for this subset. Requests are size-limited and loops are
capped at 100,000 iterations to prevent a runaway request.

## AI features

Two optional AI-powered features live on top of the (fully deterministic, non-AI) compiler
pipeline above — the pipeline's own analysis never depends on the AI, so everything described
earlier works identically whether or not AI is configured:

1. **Ask AI** — a floating chat panel (bottom-right, on every phase) where you can ask general
   compiler-theory questions ("what's the difference between a triple and a quadruple?") or
   questions grounded in the program you currently have open ("why did the optimizer remove line
   3?"). It's sent your current language, source code, active tab, and the analysis JSON so far,
   so answers can reference your actual variable names, instructions, and numbers.
2. **Generate AI Report** (on the Summary tab) — writes one cohesive, phase-by-phase Markdown
   report explaining exactly what happened when *your* program went through the pipeline: the
   real tokens, the real AST shape, the real TAC/quadruples/triples/indirect-triples, which
   optimizations fired and why, what the target code does, and the real output — not a generic
   description. Downloadable as a `.md` file.

The AI features support **NVIDIA Nemotron** (free API via NVIDIA NIM / build.nvidia.com)
or the **Anthropic API** from the backend only — your API key is never sent to, or
readable from, the browser. **They're optional**: with no key configured, the rest of the app
works exactly as before, and the AI panel/report just show a message explaining how to enable them.

**Enabling AI features with NVIDIA Nemotron (Free):**
```powershell
$env:NVIDIA_API_KEY="nvapi-..."               # on Linux/macOS: export NVIDIA_API_KEY="nvapi-..."
uvicorn backend.main:app --reload --port 8000
```
*(Optionally override model, defaults to `nvidia/nemotron-3-ultra-550b-a55b`: `$env:NVIDIA_MODEL="nvidia/llama-3.1-nemotron-70b-instruct"`)*

**Or enabling with Anthropic:**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."          # on Linux/macOS: export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn backend.main:app --reload --port 8000
```
If neither key is set, `GET /api/ai-status` reports `{"configured": false}` and the UI surfaces a
one-line note instead of failing silently.

## Uploading a code file

Next to **▶ Analyze** is an **⇧ Upload Code File** button. It accepts `.c .cc .cpp .cxx .h .hpp
.java .py .txt` files, reads them client-side (no file is sent anywhere until you click Analyze),
drops the contents into the editor, and — for recognized extensions — automatically switches the
language dropdown to match (e.g. a `.py` file switches to Python). `.txt` files load as-is without
changing the selected language, since the extension doesn't imply one.

## Pinpointing errors exactly

Whenever a program fails at any phase — lexical, syntax, semantic, or at runtime — the app:
- **Jumps you straight to the phase where it happened** (no hunting through tabs).
- Shows a **persistent red banner** above the phase list naming the phase and line, from any tab,
  so you don't lose track of it while exploring other phases — click it to jump back.
- Shows an **Error Explorer** card with the exact phase, line, column (when available), error
  kind, and a **highlighted source snippet** — the exact offending line, marked, with a few lines
  of surrounding context and a `^-- here` column marker where relevant.
- Includes a **"🧠 Ask AI to explain this error"** button that sends the precise error details to
  the AI assistant for a plain-language explanation and fix suggestion (requires `ANTHROPIC_API_KEY`).

This covers every error class the pipeline can produce, including runtime errors (division by
zero, undefined-variable use, etc.), which are now line-accurate too.

## PDF compilation report

On the **Summary** tab, **📄 Full PDF Report** builds one PDF covering the entire run: source
code, tokens, AST, every expression's tree/postfix, the symbol table, TAC + quadruples + triples +
indirect triples, optimizations (before/after), target code, and execution output — or, if the
pipeline stopped early, a dedicated error section with the same highlighted code snippet the web
UI shows. If you've already generated the AI narrative report above it, that's appended as a
final section automatically.

- **View PDF** opens it in an in-app modal (no new tab, no separate download needed).
- **Download PDF** saves it locally.

This feature needs no AI key — it's built from the same deterministic pipeline data as the rest
of the app; the AI report section is simply appended if you happen to have generated one first.

## Requirements

- Python 3.9+
- No Node.js / npm needed — the frontend is plain HTML/CSS/JS, no build step.

## How to run it

**1. Install backend dependencies**
```bash
cd explainable-compiler
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

**2. (Optional) Enable the AI assistant / AI report**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
Skip this and everything still works — you just won't see AI answers/reports (see "AI features" above).

**3. Start the server** (run from the project root, not from inside `backend/`)
```bash
uvicorn backend.main:app --reload --port 8000
```

**4. Open the app**

Visit **http://localhost:8000** in your browser. The backend serves the frontend directly, so
that's the only URL you need — no separate frontend server, no CORS setup required.

You should see the language selector, a code editor pre-filled with a C example, and an
**Analyze** button. Pick a language, edit the code (or choose one of the built-in examples), then
click **Analyze** to step through preprocessing → lexical → syntax → semantic → symbol table →
intermediate code → optimization → target code → execution → summary.

### Running frontend and backend separately (optional)

If you'd rather serve the frontend from its own static server (e.g. VS Code's Live Server, or
`python3 -m http.server` inside `frontend/`), that works too — just make sure the backend is also
running (step 2 above). The frontend auto-detects the backend at `http://localhost:8000` if it
isn't being served from the same origin. Only change this if your backend runs on a different
host/port: edit the `API_BASE` fallback list at the top of `frontend/app.js`.

### Quick API check (no browser needed)

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"language":"c","code":"int a = 10;\nint b = 20;\nint sum = a + b;\nprintf(\"%d\", sum);","input":""}'
```

## API

| Method | Path             | Description                                            |
|--------|------------------|---------------------------------------------------------|
| GET    | `/api/health`    | Liveness check                                          |
| GET    | `/api/languages` | Supported languages, their pipeline order, sample code |
| POST   | `/api/analyze`   | Run the full phase pipeline. Body: `{language, code, input}` |
| GET    | `/api/ai-status` | Whether an `ANTHROPIC_API_KEY` is configured server-side |
| POST   | `/api/ask`       | Ask the AI assistant a question. Body: `{question, language, code, activePhase, phases}` (all but `question` optional) |
| POST   | `/api/report`    | Generate an AI-written Markdown report for one analysis. Body: `{language, code, phases}` (the `phases` object from `/api/analyze`) |
| POST   | `/api/pdf-report`| Generate a full PDF report for one analysis (viewable/downloadable). Body: `{language, code, phases, status, error, aiReport}` — `error` and `aiReport` are optional |

`POST /api/analyze` returns one JSON object containing every phase's result (`phases`), a
per-phase status (`status`: `ok` / `err` / `na`), and, if something failed, a structured `error`
(`phase`, `line`, `message`, and `expected`/`received` for syntax errors).

`POST /api/ask` and `POST /api/report` return `400` with a plain-English `detail` message if no
`ANTHROPIC_API_KEY` is configured, or if the underlying API call fails — this is expected and
handled gracefully by the UI.

## Extending it

Each phase is its own module, so extending the subset is localized:
- Add a construct (e.g. `for` loops): extend `parser_.py`'s grammar, then `ir.py` / `executor.py`
  to handle the new AST node type.
- Add a language: add an entry to `languages/config.py` and extend `parser_.py`'s brace/indent
  branch as needed.
- Add an optimization pass: add a function to `optimizer.py` and append its notes to the `notes` list.

Natural next steps not included in this build: Marathi/Hindi explanation translations, a database
of saved programs/analysis history, and a real sandboxed backend that compiles/runs actual
gcc/g++/javac/python source (as opposed to this subset's built-in interpreter). The AI
assistant/report described above is already included.

## License

Use, modify, and extend freely for coursework or teaching.
