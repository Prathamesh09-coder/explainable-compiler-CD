"""Phase: Target Code Generation (educational instruction-style representation)."""

ARITH_NAMES = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV",
               "==": "CMPEQ", "!=": "CMPNE", "<": "CMPLT", ">": "CMPGT", "<=": "CMPLE", ">=": "CMPGE"}


def gen_target(code):
    lines = []
    reg = 1
    for l in code:
        op = l["op"]
        if op == "=":
            lines.append(f"LOAD R{reg}, {l['a1']}")
            lines.append(f"STORE R{reg}, {l['res']}")
            reg = (reg % 6) + 1
        elif op in ARITH_NAMES:
            name = ARITH_NAMES[op]
            lines.append(f"LOAD R1, {l['a1']}")
            lines.append(f"LOAD R2, {l['a2']}")
            lines.append(f"{name} R1, R2")
            lines.append(f"STORE R1, {l['res']}")
        elif op == "PRINT":
            lines.append(f"LOAD R1, {l['a1']}")
            lines.append("PRINT R1")
        elif op == "LABEL":
            lines.append(f"{l['res']}:")
        elif op == "GOTO":
            lines.append(f"JMP {l['res']}")
        elif op == "IFFALSE":
            lines.append(f"LOAD R1, {l['a1']}")
            lines.append(f"JZ R1, {l['res']}")
        elif op == "READ":
            lines.append("READ R1")
            lines.append(f"STORE R1, {l['res']}")
    return lines
