"""
Generates a single downloadable/viewable PDF covering every phase of one
/api/analyze run: source, tokens, AST, expression trees (as text), symbol
table, three-address code + quadruples/triples/indirect triples,
optimizations, target code, execution, and -- if the phase stopped early --
a precise error explanation with a highlighted code snippet, matching what
the web UI's "Error Explorer" shows.

Uses reportlab (pure-Python, no system binaries needed). Built once per
request and returned as raw bytes; the API layer decides how to serve them.
"""
import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Preformatted, KeepTogether, HRFlowable,
)

PHASE_LABELS = {
    "preprocess": "1. Preprocessing", "lexical": "2. Lexical Analysis",
    "syntax": "3. Syntax Analysis", "expressions": "4. Expression Trees & Postfix",
    "semantic": "5. Semantic Analysis", "symtab": "6. Symbol Table",
    "ir": "7. Intermediate Code", "optimize": "8. Optimization",
    "target": "9. Target Code", "execute": "10. Execution", "summary": "11. Summary",
}

# reportlab's built-in fonts (Helvetica/Courier) only cover Latin-1 -- swap
# the Unicode glyphs the rest of the app uses for plain ASCII equivalents so
# nothing renders as a missing-glyph box.
_UNI_SAFE = {
    "\u2192": "->", "\u2190": "<-", "\u2013": "-", "\u2014": "--",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u2713": "OK", "\u2717": "X", "\u25cb": "o",
    "\u25b6": ">", "\u00d7": "x", "\u2264": "<=", "\u2265": ">=",
    "\u2260": "!=",
}


def _safe(text):
    text = "" if text is None else str(text)
    for u, a in _UNI_SAFE.items():
        text = text.replace(u, a)
    return text


def _esc(text):
    text = _safe(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1x", parent=ss["Heading1"], textColor=colors.HexColor("#1b3a5c"),
                           spaceBefore=6, spaceAfter=10))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=colors.HexColor("#2c6e49"),
                           spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("BodyX", parent=ss["BodyText"], fontSize=9.5, leading=13.5))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8, leading=11,
                           textColor=colors.HexColor("#555555")))
    ss.add(ParagraphStyle("Mono", parent=ss["Code"], fontName="Courier", fontSize=8, leading=10.5))
    ss.add(ParagraphStyle("ErrTitle", parent=ss["Heading2"], textColor=colors.HexColor("#a83a2a")))
    return ss


def _table(rows, header, col_widths=None):
    data = [header] + [[_safe(c) for c in row] for row in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b3a5c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _code_snippet_flowable(src, line, col, styles):
    if not src or not line:
        return None
    lines = src.split("\n")
    lo, hi = max(1, line - 2), min(len(lines), line + 2)
    out = []
    for n in range(lo, hi + 1):
        marker = ">> " if n == line else "   "
        out.append(f"{marker}{n:>4} | {lines[n - 1]}")
        if n == line and col:
            out.append("        | " + (" " * max(0, col - 1)) + "^-- here")
    return Preformatted(_safe("\n".join(out)), styles["Mono"])


def _fmt_tac_line(l, idx=None):
    n = f"{idx + 1}. " if idx is not None else ""
    op = l["op"]
    if op == "=":
        return f"{n}{l['res']} = {l['a1']}"
    if op == "PRINT":
        return f"{n}PRINT {l['a1']}"
    if op == "LABEL":
        return f"{n}{l['res']}:"
    if op == "GOTO":
        return f"{n}goto {l['res']}"
    if op == "IFFALSE":
        return f"{n}ifFalse {l['a1']} goto {l['res']}"
    if op == "READ":
        return f"{n}{l['res']} = read()"
    return f"{n}{l['res']} = {l['a1']} {op} {l['a2']}"


def _md_to_flowables(md, styles):
    """Minimal Markdown -> flowables for the optional AI-written report text
    (headings, **bold**, `code`, fenced code blocks, bullet lists)."""
    flow = []
    blocks = re.split(r"```([\s\S]*?)```", md or "")
    for i, chunk in enumerate(blocks):
        if i % 2 == 1:
            flow.append(Preformatted(_safe(chunk.strip("\n")), styles["Mono"]))
            continue
        for raw_line in chunk.split("\n"):
            line = raw_line.rstrip()
            if not line.strip():
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", line)
            if m:
                level = len(m.group(1))
                style = styles["H1x"] if level <= 2 else styles["H2x"]
                flow.append(Paragraph(_inline_md(m.group(2)), style))
                continue
            m = re.match(r"^\s*[-*]\s+(.*)$", line)
            if m:
                flow.append(Paragraph("&bull;&nbsp;&nbsp;" + _inline_md(m.group(1)), styles["BodyX"]))
                continue
            flow.append(Paragraph(_inline_md(line), styles["BodyX"]))
    return flow


def _inline_md(text):
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
    return text


def build_pdf_bytes(language, code, phases, status, error, ai_report_text=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                             title="Explainable Compiler - Compilation Report")
    styles = _styles()
    story = []
    lang_names = {"c": "C", "cpp": "C++", "java": "Java", "python": "Python"}

    # ---- title page ----
    story.append(Paragraph("Explainable Compiler", styles["Title"]))
    story.append(Paragraph("Full Compilation Report", styles["H1x"]))
    story.append(Paragraph(f"Language: <b>{lang_names.get(language, language)}</b>", styles["BodyX"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Small"]))
    overall = "Completed successfully" if not error else f"Stopped at: {PHASE_LABELS.get(error['phase'], error['phase'])}"
    story.append(Paragraph(f"Result: <b>{_esc(overall)}</b>", styles["BodyX"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Source Code", styles["H2x"]))
    story.append(Preformatted(_safe(code), styles["Mono"]))
    story.append(PageBreak())

    # ---- error, if any (shown prominently, right after the source) ----
    if error:
        story.append(Paragraph("Error Explorer - exactly what's wrong, and where", styles["ErrTitle"]))
        rows = [["Phase", PHASE_LABELS.get(error["phase"], error["phase"])]]
        if error.get("line"):
            loc = str(error["line"]) + (f", column {error['col']}" if error.get("col") else "")
            rows.append(["Line", loc])
        if error.get("kind"):
            rows.append(["Type", error["kind"]])
        if error.get("expected"):
            rows.append(["Expected", str(error["expected"])])
        if error.get("received"):
            rows.append(["Found", str(error["received"])])
        t = Table(rows, colWidths=[1.3 * inch, 4.7 * inch])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f8")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))
        snippet = _code_snippet_flowable(code, error.get("line"), error.get("col"), styles)
        if snippet:
            story.append(snippet)
            story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Explanation:</b> {_esc(error['message'])}", styles["BodyX"]))
        story.append(Paragraph(
            f"Go back to the code editor, fix line {error.get('line', '?')}, and re-run Analyze.",
            styles["BodyX"]))
        story.append(PageBreak())

    # ---- preprocessing ----
    pre = phases.get("preprocess")
    if pre:
        story.append(Paragraph(PHASE_LABELS["preprocess"], styles["H1x"]))
        if pre.get("note"):
            story.append(Paragraph(_esc(pre["note"]), styles["BodyX"]))
        else:
            if pre.get("directives"):
                story.append(_table([[d["text"], d["explain"]] for d in pre["directives"]],
                                     ["Directive", "Meaning"], [1.8 * inch, 4.2 * inch]))
            else:
                story.append(Paragraph("No preprocessor directives found.", styles["BodyX"]))
        story.append(Spacer(1, 10))

    # ---- lexical ----
    lex = phases.get("lexical")
    if lex:
        story.append(Paragraph(PHASE_LABELS["lexical"], styles["H1x"]))
        toks = [t for t in lex["tokens"] if t["t"] not in ("COMMENT", "PREPROC")]
        rows = [[t["line"], t["v"], "ILLEGAL" if t.get("error") else t["t"], t["cat"]] for t in toks[:400]]
        if rows:
            story.append(_table(rows, ["Line", "Lexeme", "Token", "Category"],
                                 [0.6 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch]))
            if len(toks) > 400:
                story.append(Paragraph(f"... {len(toks) - 400} more tokens omitted for length ...", styles["Small"]))
        story.append(Spacer(1, 10))

    # ---- syntax ----
    syn = phases.get("syntax")
    if syn:
        story.append(Paragraph(PHASE_LABELS["syntax"], styles["H1x"]))
        rows = [[i + 1, s["type"], s["line"]] for i, s in enumerate(syn["ast"])]
        if rows:
            story.append(_table(rows, ["#", "Statement type", "Line"], [0.6 * inch, 2.5 * inch, 0.8 * inch]))
        story.append(Spacer(1, 10))

    # ---- expressions ----
    expr = phases.get("expressions")
    if expr and expr.get("list"):
        story.append(Paragraph(PHASE_LABELS["expressions"], styles["H1x"]))
        for i, e in enumerate(expr["list"]):
            story.append(Paragraph(f"Expression {i + 1} - {_esc(e['context'])} (line {e['line']})", styles["H2x"]))
            story.append(Paragraph(f"<b>Infix:</b> <font face='Courier'>{_esc(e['infix'])}</font>", styles["BodyX"]))
            story.append(Paragraph(f"<b>Postfix:</b> <font face='Courier'>{_esc(e['postfix'])}</font>", styles["BodyX"]))
        story.append(Spacer(1, 10))

    # ---- semantic + symbol table ----
    sem = phases.get("semantic")
    symtab = phases.get("symtab")
    if sem is not None:
        story.append(Paragraph(PHASE_LABELS["semantic"], styles["H1x"]))
        if sem.get("dynamicTyping"):
            story.append(Paragraph("This language is dynamically typed, so type-mismatch checks are relaxed.",
                                    styles["BodyX"]))
        if not sem.get("errors"):
            story.append(Paragraph("No semantic errors found.", styles["BodyX"]))
    if symtab and symtab.get("symtab"):
        story.append(Paragraph(PHASE_LABELS["symtab"], styles["H2x"]))
        rows = [[r["name"], r["type"], r["kind"], r["scope"], r["line"],
                 "-" if r.get("value") is None else r["value"]] for r in symtab["symtab"]]
        story.append(_table(rows, ["Name", "Type", "Kind", "Scope", "Line", "Value"],
                             [0.9 * inch, 0.7 * inch, 0.8 * inch, 1.1 * inch, 0.5 * inch, 1.0 * inch]))
        story.append(Spacer(1, 10))

    # ---- IR: TAC / quadruples / triples / indirect triples ----
    ir = phases.get("ir")
    if ir:
        story.append(PageBreak())
        story.append(Paragraph(PHASE_LABELS["ir"], styles["H1x"]))
        story.append(Paragraph("Three-Address Code (TAC)", styles["H2x"]))
        story.append(Preformatted(_safe("\n".join(_fmt_tac_line(l, i) for i, l in enumerate(ir["tac"]))), styles["Mono"]))
        story.append(Paragraph("Quadruples", styles["H2x"]))
        story.append(_table(
            [[q["index"] + 1, q["op"], q["arg1"] if q["arg1"] is not None else "-",
              q["arg2"] if q["arg2"] is not None else "-", q["result"] if q["result"] is not None else "-"]
             for q in ir["quadruples"]],
            ["#", "Op", "Arg1", "Arg2", "Result"], [0.4 * inch, 0.9 * inch, 1.3 * inch, 1.3 * inch, 1.3 * inch]))
        story.append(Paragraph("Triples", styles["H2x"]))
        story.append(_table(
            [[t["index"], t["op"], t["arg1"] if t["arg1"] is not None else "-",
              t["arg2"] if t["arg2"] is not None else "-"] for t in ir["triples"]],
            ["#", "Op", "Arg1", "Arg2"], [0.4 * inch, 0.9 * inch, 1.8 * inch, 1.8 * inch]))
        story.append(Paragraph("Indirect Triples", styles["H2x"]))
        story.append(_table(
            [[p["stmt"], f"({p['ptr']})"] for p in ir["indirectTriples"]],
            ["Statement", "-> Triple #"], [1.2 * inch, 1.2 * inch]))
        if ir.get("llvm") and ir["llvm"].get("raw"):
            story.append(Paragraph("LLVM IR (Industry Standard SSA Form)", styles["H2x"]))
            story.append(Preformatted(_safe(ir["llvm"]["raw"][:4000]), styles["Mono"]))
        story.append(Spacer(1, 10))

    # ---- optimization ----
    opt = phases.get("optimize")
    if opt:
        story.append(Paragraph(PHASE_LABELS["optimize"], styles["H1x"]))
        story.append(Paragraph(f"Instructions before: {len(ir['tac']) if ir else '?'} -> after: {len(opt['code'])}",
                                styles["BodyX"]))
        if opt.get("notes"):
            for n in opt["notes"]:
                story.append(Paragraph(f"<b>[{_esc(n['rule'])}]</b> {_esc(n['before'])} - {_esc(n['detail'])}",
                                        styles["BodyX"]))
        else:
            story.append(Paragraph("No safe optimization opportunities were found.", styles["BodyX"]))
        story.append(Paragraph("Optimized Three-Address Code", styles["H2x"]))
        story.append(Preformatted(_safe("\n".join(_fmt_tac_line(l, i) for i, l in enumerate(opt["code"]))), styles["Mono"]))
        story.append(Spacer(1, 10))

    # ---- target ----
    tgt = phases.get("target")
    if tgt:
        story.append(Paragraph(PHASE_LABELS["target"], styles["H1x"]))
        story.append(Preformatted(_safe("\n".join(tgt["lines"])), styles["Mono"]))
        story.append(Spacer(1, 10))

    # ---- execution ----
    ex = phases.get("execute")
    if ex:
        story.append(Paragraph(PHASE_LABELS["execute"], styles["H1x"]))
        if ex.get("error"):
            story.append(Paragraph(f"<b>Runtime Error:</b> {_esc(ex['error'])}", styles["BodyX"]))
        else:
            story.append(Paragraph("Program Output:", styles["BodyX"]))
            story.append(Preformatted(_safe(ex.get("output") or "(no output)"), styles["Mono"]))
        story.append(Spacer(1, 10))

    # ---- optional AI-written narrative report ----
    if ai_report_text:
        story.append(PageBreak())
        story.append(Paragraph("AI Compilation Report", styles["H1x"]))
        story.extend(_md_to_flowables(ai_report_text, styles))

    doc.build(story)
    return buf.getvalue()
