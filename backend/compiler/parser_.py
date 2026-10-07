"""
Phase: Syntax Analysis.

A hand-written recursive-descent parser for the shared educational subset:
  VarDecl, Assign, Print, If, While, Return
  Expr -> Term (('+'|'-') Term)*
  Term -> Factor (('*'|'/') Factor)*
  Factor -> NUMBER | STRING | IDENT | '(' Expr ')' | input()
  Cond -> Expr (('=='|'!='|'<'|'>'|'<='|'>=') Expr)?

C/C++/Java share a brace-and-semicolon grammar; Python uses indentation.
Both branches build the same AST node shapes so later phases are language-agnostic.
"""
from .lexer import tokenize

TYPES = {"int", "float", "double", "char", "void", "String"}
COMPARE_OPS = {"==", "!=", "<", ">", "<=", ">="}


class ParseError(Exception):
    def __init__(self, message, line, expected=None, received=None, col=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.expected = expected
        self.received = received
        self.col = col


def parse_program(body: str, lang: str, keywords):
    style = "indent" if lang == "python" else "brace"
    if style == "indent":
        return parse_python(body)
    return parse_brace(body, lang, keywords)


# ---------------------------------------------------------------- brace style
def parse_brace(text, lang, keywords):
    toks = [t for t in tokenize(text, lang, keywords) if t["t"] not in ("COMMENT", "PREPROC")]
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def advance():
        t = peek()
        pos[0] += 1
        return t

    def expect(v):
        t = advance()
        if not t or t["v"] != v:
            prev_line = toks[pos[0] - 2]["line"] if pos[0] - 2 >= 0 else 1
            raise ParseError(f"Expected '{v}'", t["line"] if t else prev_line, v, t["v"] if t else "end of input",
                              col=t.get("col") if t else None)
        return t

    def expect_semi(line):
        t = advance()
        if not t or t["v"] != ";":
            raise ParseError("Missing ';'", line, "';'", t["v"] if t else "end of input",
                              col=t.get("col") if t else None)

    def parse_statements():
        stmts = []
        while peek() and peek()["v"] != "}":
            stmts.append(parse_statement())
        return stmts

    def parse_block():
        expect("{")
        s = parse_statements()
        expect("}")
        return s

    def parse_print_arg():
        if peek() and peek()["t"] == "STRING_LITERAL":
            return {"type": "Str", "value": advance()["v"]}
        return parse_expr()

    def parse_statement():
        t = peek()
        if not t:
            prev = toks[pos[0] - 1]["line"] if toks else 1
            raise ParseError("Unexpected end of input", prev, "statement", "end of input")
        if t["cat"] == "Keyword" and t["v"] in TYPES:
            line = t["line"]; vtype = advance()["v"]; idt = advance()
            if not idt or idt["cat"] != "Identifier":
                raise ParseError("Expected identifier after type", line, "identifier", idt["v"] if idt else "end")
            expr = None
            if peek() and peek()["v"] == "=":
                advance(); expr = parse_expr()
            expect_semi(line)
            return {"type": "VarDecl", "varType": vtype, "name": idt["v"], "expr": expr, "line": line}
        if t["v"] == "if":
            line = advance()["line"]; expect("("); cond = parse_cond(); expect(")")
            then_b = parse_block(); else_b = []
            if peek() and peek()["v"] == "else":
                advance(); else_b = parse_block()
            return {"type": "If", "cond": cond, "then": then_b, "else": else_b, "line": line}
        if t["v"] == "while":
            line = advance()["line"]; expect("("); cond = parse_cond(); expect(")")
            body = parse_block()
            return {"type": "While", "cond": cond, "body": body, "line": line}
        if t["v"] == "return":
            line = advance()["line"]; e = None
            if peek() and peek()["v"] != ";":
                e = parse_expr()
            expect_semi(line)
            return {"type": "Return", "expr": e, "line": line}
        if t["v"] == "printf":
            line = advance()["line"]; expect("("); args = [parse_print_arg()]
            while peek() and peek()["v"] == ",":
                advance(); args.append(parse_print_arg())
            expect(")"); expect_semi(line)
            return {"type": "Print", "args": args, "line": line}
        if t["v"] == "cout":
            line = advance()["line"]; args = []
            while peek() and peek()["v"] == "<<":
                advance(); args.append(parse_expr())
            expect_semi(line)
            return {"type": "Print", "args": args, "line": line}
        if t["v"] == "System":
            line = advance()["line"]; expect("."); advance(); expect("."); advance(); expect("(")
            args = []
            if peek() and peek()["v"] != ")":
                args.append(parse_expr())
                while peek() and peek()["v"] == ",":
                    advance(); args.append(parse_expr())
            expect(")"); expect_semi(line)
            return {"type": "Print", "args": args, "line": line}
        if t["cat"] == "Identifier":
            line = advance()["line"]  # consumed name already below fix
            name = t["v"]
            expect("="); expr = parse_expr(); expect_semi(line)
            return {"type": "Assign", "name": name, "expr": expr, "line": line}
        raise ParseError(f"Unexpected token '{t['v']}'", t["line"], "statement", t["v"], col=t.get("col"))

    def parse_cond():
        left = parse_expr()
        t = peek()
        if t and t["v"] in COMPARE_OPS:
            op = advance()["v"]
            return {"type": "Compare", "op": op, "left": left, "right": parse_expr()}
        return left

    def parse_expr():
        n = parse_term()
        while peek() and peek()["v"] in ("+", "-"):
            op = advance()["v"]
            n = {"type": "BinOp", "op": op, "left": n, "right": parse_term()}
        return n

    def parse_term():
        n = parse_factor()
        while peek() and peek()["v"] in ("*", "/"):
            op = advance()["v"]
            n = {"type": "BinOp", "op": op, "left": n, "right": parse_factor()}
        return n

    def parse_factor():
        t = peek()
        if not t:
            prev = toks[pos[0] - 1]["line"] if toks else 1
            raise ParseError("Unexpected end of expression", prev, "operand", "end of input")
        if t["v"] == "(":
            advance(); e = parse_expr(); expect(")"); return e
        if t["t"] in ("INTEGER_LITERAL", "FLOAT_LITERAL"):
            advance(); return {"type": "Num", "value": float(t["v"]) if "." in t["v"] else int(t["v"])}
        if t["t"] == "STRING_LITERAL":
            advance(); return {"type": "Str", "value": t["v"]}
        if t["cat"] == "Identifier":
            advance(); return {"type": "Id", "name": t["v"]}
        raise ParseError(f"Unexpected token '{t['v']}' in expression", t["line"], "number, identifier or (", t["v"], col=t.get("col"))

    return parse_statements()


# ------------------------------------------------------------- python style
def parse_python(text):
    raw_lines = [l for l in text.split("\n") if l.strip()]
    lines = []
    all_lines = text.split("\n")
    li = 0
    for l in raw_lines:
        indent = len(l) - len(l.lstrip(" "))
        stripped = l.strip()
        while li < len(all_lines) and all_lines[li].strip() != stripped:
            li += 1
        lines.append({"indent": indent, "text": stripped, "lineNo": li + 1})
        li += 1
    idx = [0]

    def tok_line(s):
        return [t for t in tokenize(s, "python", ["input"]) if t["t"] != "COMMENT"]

    def expr_from_tokens(toks):
        p = [0]

        def peek():
            return toks[p[0]] if p[0] < len(toks) else None

        def advance():
            t = peek(); p[0] += 1; return t

        def parse_expr():
            n = parse_term()
            while peek() and peek()["v"] in ("+", "-"):
                op = advance()["v"]
                n = {"type": "BinOp", "op": op, "left": n, "right": parse_term()}
            return n

        def parse_term():
            n = parse_factor()
            while peek() and peek()["v"] in ("*", "/"):
                op = advance()["v"]
                n = {"type": "BinOp", "op": op, "left": n, "right": parse_factor()}
            return n

        def parse_factor():
            t = peek()
            if not t:
                raise ParseError("Unexpected end of expression", 0, "operand", "end of line")
            if t["v"] == "(":
                advance(); e = parse_expr(); advance(); return e
            if t["t"] in ("INTEGER_LITERAL", "FLOAT_LITERAL"):
                advance(); return {"type": "Num", "value": float(t["v"]) if "." in t["v"] else int(t["v"])}
            if t["t"] == "STRING_LITERAL":
                advance(); return {"type": "Str", "value": t["v"]}
            if t["v"] == "input":
                advance(); advance(); advance()
                return {"type": "Input"}
            if t["cat"] == "Identifier":
                advance(); return {"type": "Id", "name": t["v"]}
            raise ParseError(f"Unexpected token '{t['v']}' in expression", 0, "number, identifier or (", t["v"])

        def parse_cond():
            left = parse_expr()
            t = peek()
            if t and t["v"] in COMPARE_OPS:
                op = advance()["v"]
                return {"type": "Compare", "op": op, "left": left, "right": parse_expr()}
            return left

        return parse_cond()

    def split_args(s):
        out = []; depth = 0; cur = ""
        for ch in s:
            if ch == "(":
                depth += 1
            if ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur); cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur)
        return out

    def parse_line(min_indent):
        raw = lines[idx[0]]
        line = raw["lineNo"]
        if raw["text"].startswith("if "):
            cond = raw["text"][3:raw["text"].rfind(":")].strip()
            idx[0] += 1
            then_b = parse_block(min_indent + 4)
            else_b = []
            if idx[0] < len(lines) and lines[idx[0]]["indent"] == min_indent and lines[idx[0]]["text"].startswith("else"):
                idx[0] += 1
                else_b = parse_block(min_indent + 4)
            return {"type": "If", "cond": expr_from_tokens(tok_line(cond)), "then": then_b, "else": else_b, "line": line}
        if raw["text"].startswith("while "):
            cond = raw["text"][6:raw["text"].rfind(":")].strip()
            idx[0] += 1
            body = parse_block(min_indent + 4)
            return {"type": "While", "cond": expr_from_tokens(tok_line(cond)), "body": body, "line": line}
        if raw["text"].startswith("print("):
            inner = raw["text"][raw["text"].index("(") + 1: raw["text"].rindex(")")]
            parts = split_args(inner)
            idx[0] += 1
            return {"type": "Print", "args": [expr_from_tokens(tok_line(a.strip())) for a in parts], "line": line}
        eq = raw["text"].find("=")
        if eq > 0 and raw["text"][eq + 1:eq + 2] != "=":
            name = raw["text"][:eq].strip()
            rhs = raw["text"][eq + 1:].strip()
            idx[0] += 1
            return {"type": "Assign", "name": name, "expr": expr_from_tokens(tok_line(rhs)), "line": line}
        raise ParseError(f"Could not parse statement '{raw['text']}'", line, "assignment, if, while or print", raw["text"],
                          col=raw["indent"] + 1)

    def parse_block(min_indent):
        stmts = []
        while idx[0] < len(lines) and lines[idx[0]]["indent"] >= min_indent:
            if lines[idx[0]]["indent"] > min_indent:
                raise ParseError("Unexpected indentation", lines[idx[0]]["lineNo"], f"indent {min_indent}",
                                  f"indent {lines[idx[0]]['indent']}", col=lines[idx[0]]["indent"] + 1)
            stmts.append(parse_line(min_indent))
        return stmts

    return parse_block(0)
