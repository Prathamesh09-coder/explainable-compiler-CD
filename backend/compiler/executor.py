"""
Phase: Execution.

Runs the AST directly with a small tree-walking interpreter. This performs
no filesystem, network, subprocess, or eval() access whatsoever -- it only
manipulates a Python dict of variables -- so no OS-level sandboxing is
required for this educational subset. Loops are bounded to prevent runaway
execution from tying up a request.
"""
import re

FORMAT_RE = re.compile(r"%[dfs]")
MAX_LOOP_ITERATIONS = 100_000


class RuntimeErrorX(Exception):
    pass


def interpret(ast, stdin_text):
    env = {}
    output = []
    error = None
    error_line = None
    cur_line = [None]
    input_queue = (stdin_text or "").split()
    ptr = [0]

    def to_num_if_possible(v):
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return v

    def eval_expr(e):
        t = e["type"]
        if t == "Num":
            return e["value"]
        if t == "Str":
            return e["value"].strip('"')
        if t == "Input":
            if ptr[0] < len(input_queue):
                v = input_queue[ptr[0]]; ptr[0] += 1
                return to_num_if_possible(v)
            return 0
        if t == "Id":
            if e["name"] not in env:
                raise RuntimeErrorX(f"Runtime error: variable '{e['name']}' used before assignment")
            return env[e["name"]]
        if t == "BinOp":
            l = eval_expr(e["left"]); r = eval_expr(e["right"])
            if isinstance(l, str) or isinstance(r, str):
                if e["op"] == "+":
                    return str(l) + str(r)
                raise RuntimeErrorX(f"Runtime error: cannot apply '{e['op']}' to a string")
            if e["op"] == "/":
                if r == 0:
                    raise RuntimeErrorX("Runtime error: division by zero")
                return l / r
            return {"+": l + r, "-": l - r, "*": l * r}[e["op"]]
        if t == "Compare":
            l = eval_expr(e["left"]); r = eval_expr(e["right"])
            return {"==": l == r, "!=": l != r, "<": l < r, ">": l > r, "<=": l <= r, ">=": l >= r}[e["op"]]

    def fmt_value(v):
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    def exec_stmts(stmts):
        for s in stmts:
            t = s["type"]
            cur_line[0] = s.get("line", cur_line[0])
            if t == "VarDecl":
                env[s["name"]] = eval_expr(s["expr"]) if s["expr"] is not None else 0
            elif t == "Assign":
                env[s["name"]] = eval_expr(s["expr"])
            elif t == "Print":
                vals = [eval_expr(a) for a in s["args"]]
                if vals and isinstance(vals[0], str) and FORMAT_RE.search(vals[0]):
                    it = iter(vals[1:])
                    output.append(FORMAT_RE.sub(lambda _m: fmt_value(next(it)), vals[0]))
                else:
                    output.append("".join(fmt_value(v) for v in vals))
            elif t == "If":
                exec_stmts(s["then"] if eval_expr(s["cond"]) else s["else"])
            elif t == "While":
                guard = 0
                while eval_expr(s["cond"]):
                    exec_stmts(s["body"])
                    guard += 1
                    if guard > MAX_LOOP_ITERATIONS:
                        raise RuntimeErrorX("Runtime error: possible infinite loop (execution limit reached)")
            elif t == "Return":
                pass

    try:
        exec_stmts(ast)
    except RuntimeErrorX as e:
        error = str(e)
        error_line = cur_line[0]
    except Exception as e:  # noqa: BLE001 -- surface any unexpected interpreter fault as a runtime error, never a 500
        error = f"Runtime error: {e}"
        error_line = cur_line[0]

    return {"output": "\n".join(output), "env": env, "error": error, "line": error_line}
