from .lexer import preprocess, tokenize, extract_body
from .parser_ import parse_program, ParseError
from .semantic import analyze_semantics
from .ir import (
    gen_ir, fmt_tac, gen_quadruples, gen_triples, gen_indirect_triples,
    collect_expressions,
)
from .optimizer import optimize
from .target import gen_target
from .executor import interpret
from .llvm_ir import gen_llvm_ir
from backend.languages.config import LANGS


def run_pipeline(lang: str, src: str, stdin_text: str):
    keywords = LANGS[lang]["keywords"]
    pipeline_order = LANGS[lang]["pipeline"]
    status = {p: "pending" for p in pipeline_order}
    phases = {}
    error = None

    # ---- preprocessing ----
    pre = preprocess(src, lang)
    phases["preprocess"] = pre
    if "preprocess" in status:
        status["preprocess"] = "ok"
    body_src = pre["body"]

    # ---- lexical analysis ----
    tokens = tokenize(body_src, lang, keywords)
    phases["lexical"] = {"tokens": tokens}
    illegal = [t for t in tokens if t.get("error")]
    if illegal:
        status["lexical"] = "err"
        error = {"phase": "lexical", "message": f"Illegal character '{illegal[0]['v']}'",
                 "line": illegal[0]["line"], "col": illegal[0].get("col")}
        _mark_rest_na(status, pipeline_order, "lexical")
        return _response(lang, src, phases, status, error)
    status["lexical"] = "ok"

    inner_body, wrapper_note = extract_body(body_src, lang)
    phases["wrapperNote"] = wrapper_note

    # ---- syntax analysis ----
    try:
        ast = parse_program(inner_body, lang, keywords)
        phases["syntax"] = {"ast": ast}
        status["syntax"] = "ok"
    except ParseError as e:
        status["syntax"] = "err"
        error = {"phase": "syntax", "message": e.message, "line": e.line, "expected": e.expected,
                 "received": e.received, "col": e.col}
        _mark_rest_na(status, pipeline_order, "syntax")
        return _response(lang, src, phases, status, error)

    # ---- expression trees / postfix (drawn from the syntax-phase AST) ----
    phases["expressions"] = {"list": collect_expressions(ast)}
    if "expressions" in status:
        status["expressions"] = "ok"

    # ---- semantic analysis + symbol table ----
    sem = analyze_semantics(ast, lang)
    phases["semantic"] = {"errors": sem["errors"], "dynamicTyping": sem["dynamicTyping"]}
    phases["symtab"] = {"symtab": sem["symtab"]}
    status["semantic"] = "err" if sem["errors"] else "ok"
    status["symtab"] = "ok"
    if sem["errors"]:
        first = sem["errors"][0]
        error = {"phase": "semantic", "message": first["message"], "line": first["line"], "kind": first["kind"]}
        _mark_rest_na(status, pipeline_order, "semantic", keep=("symtab",))
        return _response(lang, src, phases, status, error)

    # ---- intermediate code ----
    tac = gen_ir(ast)
    triples = gen_triples(tac)
    llvm_ir = gen_llvm_ir(ast, sem["symtab"], lang)
    phases["ir"] = {
        "tac": tac,
        "quadruples": gen_quadruples(tac),
        "triples": triples,
        "indirectTriples": gen_indirect_triples(triples),
        "llvm": llvm_ir,
    }
    status["ir"] = "ok"

    # ---- optimization ----
    opt = optimize(tac)
    phases["optimize"] = opt
    status["optimize"] = "ok"

    # ---- target code ----
    target_lines = gen_target(opt["code"])
    phases["target"] = {"lines": target_lines}
    status["target"] = "ok"

    # ---- execution ----
    exec_result = interpret(ast, stdin_text)
    phases["execute"] = exec_result
    status["execute"] = "err" if exec_result["error"] else "ok"
    if exec_result["error"]:
        error = {"phase": "execute", "message": exec_result["error"], "line": exec_result.get("line")}

    for row in sem["symtab"]:
        row["value"] = exec_result["env"].get(row["name"])

    if "summary" in status:
        status["summary"] = "ok"

    return _response(lang, src, phases, status, error)


def _mark_rest_na(status, pipeline_order, from_phase, keep=()):
    started = False
    for p in pipeline_order:
        if p == from_phase:
            started = True
            continue
        if started and status.get(p) == "pending" and p not in keep:
            status[p] = "na"


def _response(lang, src, phases, status, error):
    return {"lang": lang, "src": src, "phases": phases, "status": status, "error": error}
