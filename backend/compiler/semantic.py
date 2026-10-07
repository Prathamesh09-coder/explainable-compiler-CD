"""
Phase: Semantic Analysis + Symbol Table.

Checks: undeclared-variable use, duplicate declaration, type mismatch on
assignment, and invalid operations between incompatible types. Python is
dynamically typed, so type-mismatch checks are relaxed there (documented
in the response) and re-binding a name to a new type is not an error.
"""


def analyze_semantics(ast, lang):
    symtab = []
    errors = []
    declared = {}
    is_static = lang != "python"

    def type_of(e, line):
        if e["type"] == "Num":
            return "int" if isinstance(e["value"], int) else "float"
        if e["type"] == "Str":
            return "string"
        if e["type"] == "Input":
            return "string"
        if e["type"] == "Id":
            d = declared.get(e["name"])
            if not d:
                errors.append({"phase": "semantic", "kind": "Undeclared variable", "line": line,
                                "message": f"Variable '{e['name']}' is used before it is declared/assigned."})
                return "unknown"
            return d["type"]
        if e["type"] in ("BinOp", "Compare"):
            l = type_of(e["left"], line); r = type_of(e["right"], line)
            if (l == "string" or r == "string") and e["type"] == "BinOp":
                errors.append({"phase": "semantic", "kind": "Invalid operation", "line": line,
                                "message": f"Operator '{e['op']}' cannot be applied between incompatible types ({l} and {r})."})
            return "float" if (l == "float" or r == "float") else l
        return "unknown"

    def walk(stmts):
        for s in stmts:
            if s["type"] == "VarDecl":
                if s["name"] in declared and is_static:
                    errors.append({"phase": "semantic", "kind": "Duplicate declaration", "line": s["line"],
                                    "message": f"Variable '{s['name']}' is already declared in this scope."})
                t = "char" if s["varType"] == "char" else ("float" if s["varType"] in ("float", "double") else "int")
                declared[s["name"]] = {"type": t, "line": s["line"]}
                symtab.append({"name": s["name"], "type": t, "kind": "Variable", "scope": "Local (main)",
                                "line": s["line"], "value": None})
                if s["expr"]:
                    rt = type_of(s["expr"], s["line"])
                    if is_static and t != "string" and rt == "string":
                        errors.append({"phase": "semantic", "kind": "Type mismatch", "line": s["line"],
                                        "message": f"The variable '{s['name']}' is declared as {t}, but a string value is assigned to it."})
            elif s["type"] == "Assign":
                entry = next((e for e in symtab if e["name"] == s["name"]), None)
                rt = type_of(s["expr"], s["line"])
                if not entry:
                    if is_static:
                        errors.append({"phase": "semantic", "kind": "Undeclared variable", "line": s["line"],
                                        "message": f"Variable '{s['name']}' is assigned to but was never declared "
                                                    f"(e.g. with 'int {s['name']} = ...;')."})
                        t = "unknown"
                    else:
                        t = rt
                    entry = {"name": s["name"], "type": t, "kind": "Variable", "scope": "Local (main)",
                             "line": s["line"], "value": None}
                    symtab.append(entry)
                    declared[s["name"]] = {"type": t, "line": s["line"]}
                elif is_static and entry["type"] != "string" and rt == "string":
                    errors.append({"phase": "semantic", "kind": "Type mismatch", "line": s["line"],
                                    "message": f"The variable '{s['name']}' is declared as {entry['type']}, but a string value is assigned to it."})
                elif lang == "python":
                    entry["type"] = rt
            elif s["type"] == "Print":
                for a in s["args"]:
                    type_of(a, s["line"])
            elif s["type"] == "If":
                type_of(s["cond"], s["line"]); walk(s["then"]); walk(s["else"])
            elif s["type"] == "While":
                type_of(s["cond"], s["line"]); walk(s["body"])
            elif s["type"] == "Return":
                if s["expr"]:
                    type_of(s["expr"], s["line"])

    walk(ast)
    return {"symtab": symtab, "errors": errors, "dynamicTyping": not is_static}
