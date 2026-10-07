"""Phase: Intermediate Code Generation (classic Three-Address Code)."""


def gen_ir(ast):
    counters = {"temp": 0, "label": 0}
    code = []

    def new_temp():
        counters["temp"] += 1
        return f"t{counters['temp']}"

    def new_label():
        counters["label"] += 1
        return f"L{counters['label']}"

    def gen_expr(e):
        if e["type"] == "Num":
            return e["value"]
        if e["type"] == "Str":
            return e["value"]
        if e["type"] == "Id":
            return e["name"]
        if e["type"] == "Input":
            t = new_temp()
            code.append({"op": "READ", "a1": None, "a2": None, "res": t})
            return t
        if e["type"] in ("BinOp", "Compare"):
            a = gen_expr(e["left"]); b = gen_expr(e["right"])
            t = new_temp()
            code.append({"op": e["op"], "a1": a, "a2": b, "res": t})
            return t

    def walk(stmts):
        for s in stmts:
            if s["type"] == "VarDecl":
                if s["expr"] is not None:
                    v = gen_expr(s["expr"])
                    code.append({"op": "=", "a1": v, "a2": None, "res": s["name"]})
            elif s["type"] == "Assign":
                v = gen_expr(s["expr"])
                code.append({"op": "=", "a1": v, "a2": None, "res": s["name"]})
            elif s["type"] == "Print":
                for a in s["args"]:
                    v = gen_expr(a)
                    code.append({"op": "PRINT", "a1": v, "a2": None, "res": None})
            elif s["type"] == "If":
                c = gen_expr(s["cond"]); l_else = new_label(); l_end = new_label()
                code.append({"op": "IFFALSE", "a1": c, "a2": None, "res": l_else})
                walk(s["then"])
                code.append({"op": "GOTO", "a1": None, "a2": None, "res": l_end})
                code.append({"op": "LABEL", "a1": None, "a2": None, "res": l_else})
                walk(s["else"])
                code.append({"op": "LABEL", "a1": None, "a2": None, "res": l_end})
            elif s["type"] == "While":
                l_start = new_label(); l_end = new_label()
                code.append({"op": "LABEL", "a1": None, "a2": None, "res": l_start})
                c = gen_expr(s["cond"])
                code.append({"op": "IFFALSE", "a1": c, "a2": None, "res": l_end})
                walk(s["body"])
                code.append({"op": "GOTO", "a1": None, "a2": None, "res": l_start})
                code.append({"op": "LABEL", "a1": None, "a2": None, "res": l_end})

    walk(ast)
    return code


def fmt_tac(line, idx=None):
    n = f"{idx + 1}. " if idx is not None else ""
    op = line["op"]
    if op == "=":
        return f"{n}{line['res']} = {line['a1']}"
    if op == "PRINT":
        return f"{n}PRINT {line['a1']}"
    if op == "LABEL":
        return f"{n}{line['res']}:"
    if op == "GOTO":
        return f"{n}goto {line['res']}"
    if op == "IFFALSE":
        return f"{n}ifFalse {line['a1']} goto {line['res']}"
    if op == "READ":
        return f"{n}{line['res']} = read()"
    return f"{n}{line['res']} = {line['a1']} {op} {line['a2']}"


BINARY_OPS = {"+", "-", "*", "/", "==", "!=", "<", ">", "<=", ">="}


def gen_quadruples(tac):
    """Quadruple representation: (op, arg1, arg2, result) — one row per
    three-address instruction, with an explicit named/temp result column."""
    quads = []
    for i, l in enumerate(tac):
        quads.append({
            "index": i,
            "op": l["op"],
            "arg1": l.get("a1"),
            "arg2": l.get("a2"),
            "result": l.get("res"),
        })
    return quads


def gen_triples(tac):
    """Triple representation: (op, arg1, arg2) — no explicit result field.
    Whenever an operand is a temporary produced by an earlier triple, it is
    referenced positionally as '(i)' (the statement number of that triple)
    instead of by name, since triples don't name their own results."""
    triples = []
    temp_owner = {}  # temp name -> triple index that produced it

    def resolve(v):
        if isinstance(v, str) and v in temp_owner:
            return f"({temp_owner[v]})"
        return v

    for i, l in enumerate(tac):
        op, a1, a2, res = l["op"], l.get("a1"), l.get("a2"), l.get("res")
        if op in BINARY_OPS:
            triples.append({"index": i, "op": op, "arg1": resolve(a1), "arg2": resolve(a2)})
            temp_owner[res] = i
        elif op == "=":
            # Every '=' TAC line assigns into a real (non-temp) declared name.
            triples.append({"index": i, "op": "assign", "arg1": res, "arg2": resolve(a1)})
        elif op == "PRINT":
            triples.append({"index": i, "op": "print", "arg1": resolve(a1), "arg2": None})
        elif op == "READ":
            triples.append({"index": i, "op": "read", "arg1": None, "arg2": None})
            temp_owner[res] = i
        elif op == "LABEL":
            triples.append({"index": i, "op": "label", "arg1": res, "arg2": None})
        elif op == "GOTO":
            triples.append({"index": i, "op": "goto", "arg1": res, "arg2": None})
        elif op == "IFFALSE":
            triples.append({"index": i, "op": "iffalse", "arg1": resolve(a1), "arg2": res})
        else:
            triples.append({"index": i, "op": op, "arg1": resolve(a1), "arg2": resolve(a2)})
    return triples


def gen_indirect_triples(triples):
    """Indirect triple representation: a separate list of statement pointers
    into the (unchanged) triple table. The triple table itself never needs to
    be copied or shifted; an optimizer that wants to reorder code (e.g. code
    motion) only has to edit the pointer list. Since this pipeline performs no
    triple-level reordering, each pointer initially targets the triple at the
    same position — but the two tables are kept and displayed separately to
    show *why* the indirection is useful."""
    return [{"stmt": i, "ptr": i} for i in range(len(triples))]


def fmt_triple_operand(v):
    return "—" if v is None else v


def _paren(node, parent_prec):
    prec, s = _infix(node)
    return f"({s})" if prec < parent_prec else s


_PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "==": 0, "!=": 0, "<": 0, ">": 0, "<=": 0, ">=": 0}


def _infix(e):
    """Returns (precedence, string) for pretty-printing an expression with the
    minimum parentheses needed."""
    if e["type"] == "Num":
        return 99, str(e["value"])
    if e["type"] == "Str":
        return 99, f'"{e["value"]}"'
    if e["type"] == "Id":
        return 99, e["name"]
    if e["type"] == "Input":
        return 99, "input()"
    if e["type"] in ("BinOp", "Compare"):
        prec = _PREC.get(e["op"], 0)
        left = _paren(e["left"], prec)
        right = _paren(e["right"], prec + 1)
        return prec, f"{left} {e['op']} {right}"
    return 0, "?"


def expr_to_infix(e):
    return _infix(e)[1]


def expr_to_postfix(e):
    """Postfix (Reverse Polish) form of an expression tree, one token per
    space — produced by a post-order traversal: left, right, operator."""
    tokens = []

    def walk(n):
        if n["type"] == "Num":
            tokens.append(str(n["value"]))
        elif n["type"] == "Str":
            tokens.append(f'"{n["value"]}"')
        elif n["type"] == "Id":
            tokens.append(n["name"])
        elif n["type"] == "Input":
            tokens.append("input()")
        elif n["type"] in ("BinOp", "Compare"):
            walk(n["left"])
            walk(n["right"])
            tokens.append(n["op"])

    walk(e)
    return " ".join(tokens)


def _is_compound(e):
    return e is not None and e["type"] in ("BinOp", "Compare")


def collect_expressions(ast):
    """Walks the AST and returns every compound expression found (anything
    that is actually a tree, not a bare literal/identifier), tagged with the
    statement it came from, ready for tree visualization + postfix display."""
    found = []

    def add(node, context, line):
        if _is_compound(node):
            found.append({
                "context": context,
                "line": line,
                "infix": expr_to_infix(node),
                "postfix": expr_to_postfix(node),
                "tree": node,
            })

    def walk(stmts):
        for s in stmts:
            t = s["type"]
            if t == "VarDecl" and s.get("expr") is not None:
                add(s["expr"], f"initializer of '{s['name']}'", s["line"])
            elif t == "Assign":
                add(s["expr"], f"right-hand side of '{s['name']} ='", s["line"])
            elif t == "Print":
                for a in s["args"]:
                    add(a, "print argument", s["line"])
            elif t == "If":
                add(s["cond"], "if-condition", s["line"])
                walk(s["then"])
                walk(s["else"])
            elif t == "While":
                add(s["cond"], "while-condition", s["line"])
                walk(s["body"])

    walk(ast)
    return found
