"""
Phase: Code Optimization.

Every transformation here is applied only when it provably cannot change
what the program computes -- no speculative or unsafe rewrites.
"""
from .ir import fmt_tac

ARITH = ("+", "-", "*", "/")
ALL_OPS = ARITH + ("==", "!=", "<", ">", "<=", ">=")


def _is_num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _num(v):
    return float(v) if isinstance(v, str) else v


def optimize(code):
    cur = [dict(l) for l in code]
    notes = []

    # 1. constant propagation + folding (iterative)
    for _ in range(3):
        known = {}
        for l in cur:
            if l["op"] in ALL_OPS or l["op"] == "=":
                if l.get("a1") is not None and l["a1"] in known:
                    l["a1"] = known[l["a1"]]
                if l.get("a2") is not None and l["a2"] in known:
                    l["a2"] = known[l["a2"]]
            if l["op"] == "=" and _is_num(l["a1"]):
                known[l["res"]] = l["a1"]
            elif l["op"] in ARITH and _is_num(l["a1"]) and _is_num(l["a2"]):
                x, y = _num(l["a1"]), _num(l["a2"])
                r = None
                if l["op"] == "+":
                    r = x + y
                elif l["op"] == "-":
                    r = x - y
                elif l["op"] == "*":
                    r = x * y
                elif l["op"] == "/" and y != 0:
                    r = x / y
                if r is not None:
                    notes.append({"rule": "Constant folding", "before": fmt_tac(l),
                                  "detail": f"Both operands of '{l['op']}' are known constants ({x} and {y}), "
                                            f"so the compiler computes the result ({r}) once, at compile time, "
                                            f"instead of generating code to compute it every time the program runs."})
                    if isinstance(r, float) and r.is_integer() and isinstance(x, int) and isinstance(y, int):
                        r = int(r)
                    l["op"] = "="; l["a1"] = r; l["a2"] = None
                    known[l["res"]] = r
            else:
                known.pop(l["res"], None) if l.get("res") else None

    # 2. algebraic simplification
    for l in cur:
        if l["op"] in ("+", "-") and _is_num(l.get("a2")) and _num(l["a2"]) == 0:
            notes.append({"rule": "Algebraic simplification", "before": fmt_tac(l),
                          "detail": f"Adding or subtracting 0 never changes the value, so "
                                    f"'{l['res']} = {l['a1']} {l['op']} 0' simplifies to '{l['res']} = {l['a1']}'."})
            l["op"] = "="; l["a2"] = None
        elif l["op"] == "*" and _is_num(l.get("a2")) and _num(l["a2"]) == 1:
            notes.append({"rule": "Algebraic simplification", "before": fmt_tac(l),
                          "detail": "Multiplying by 1 never changes the value, so this simplifies to a plain copy."})
            l["op"] = "="; l["a2"] = None
        elif l["op"] == "*" and ((_is_num(l.get("a1")) and _num(l["a1"]) == 0) or
                                  (_is_num(l.get("a2")) and _num(l["a2"]) == 0)):
            notes.append({"rule": "Algebraic simplification", "before": fmt_tac(l),
                          "detail": "Multiplying by 0 always yields 0, regardless of the other operand, so the "
                                    "compiler replaces this with the constant 0."})
            l["op"] = "="; l["a1"] = 0; l["a2"] = None

    # 3. common subexpression elimination (within straight-line runs)
    for i, l in enumerate(cur):
        if l["op"] not in ARITH:
            continue
        for j in range(i - 1, -1, -1):
            p = cur[j]
            if p["op"] in ("LABEL", "GOTO", "IFFALSE"):
                break
            if p.get("res") == l.get("a1") or p.get("res") == l.get("a2"):
                break
            if p["op"] == l["op"] and p.get("a1") == l.get("a1") and p.get("a2") == l.get("a2"):
                notes.append({"rule": "Common subexpression elimination", "before": fmt_tac(l),
                              "detail": f"'{l['a1']} {l['op']} {l['a2']}' was already computed into {p['res']} "
                                        f"earlier with no changes to {l['a1']} or {l['a2']} in between, so the "
                                        f"compiler reuses {p['res']} instead of recomputing it."})
                l["op"] = "="; l["a1"] = p["res"]; l["a2"] = None
                break

    # 4. dead code elimination (temps never used again)
    changed = True
    while changed:
        changed = False
        used = set()
        for l in cur:
            for key in ("a1", "a2"):
                v = l.get(key)
                if isinstance(v, str) and not _is_num(v):
                    used.add(v)
            if l["op"] == "IFFALSE":
                used.add(l["a1"])
        keep = []
        for l in cur:
            is_temp = isinstance(l.get("res"), str) and l["res"].startswith("t")
            if l["op"] == "=" and is_temp and l["res"] not in used:
                notes.append({"rule": "Dead code elimination", "before": fmt_tac(l),
                              "detail": f"The temporary '{l['res']}' is never read anywhere afterwards (its value "
                                        f"doesn't reach a print statement or another computation), so this "
                                        f"instruction has no effect on the program's output and can be safely removed."})
                changed = True
                continue
            keep.append(l)
        cur = keep

    return {"code": cur, "notes": notes}
