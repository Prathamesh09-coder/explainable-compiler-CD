"""
Phase: LLVM Intermediate Representation Generation.

Generates clean, syntactically valid LLVM IR (.ll) from the AST,
reflecting the standard Clang/LLVM -O0 alloca/load/store memory model.

Demonstrates:
  - Strong typing (i32, double, i1, i8*)
  - Infinite SSA virtual registers (%1, %2, %3, ...)
  - Stack allocation and memory management (alloca, load, store)
  - Explicit comparisons (icmp, fcmp) and basic block branches (br, label)
  - Standard C library calls (@printf, @__isoc99_scanf)
"""
import re

FORMAT_RE = re.compile(r"%[dfs]")


def gen_llvm_ir(ast, symtab=None, lang="c"):
    reg_counter = [0]
    label_counter = [0]
    globals_list = []
    str_constants = {}
    lines = []

    def new_reg():
        reg_counter[0] += 1
        return f"%{reg_counter[0]}"

    def new_label(prefix="bb"):
        label_counter[0] += 1
        return f"{prefix}.{label_counter[0]}"

    # Map symtab types to LLVM types
    type_map = {
        "int": "i32",
        "float": "float",
        "double": "double",
        "char": "i8",
        "string": "i8*",
        "void": "void",
    }

    var_types = {}
    if symtab:
        for row in symtab:
            name = row.get("name")
            raw_t = str(row.get("type", "int")).lower()
            var_types[name] = type_map.get(raw_t, "i32")

    def get_var_type(name):
        return var_types.get(name, "i32")

    def clean_str(s):
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        return s

    def get_str_constant(raw_str):
        clean = clean_str(raw_str)
        if clean in str_constants:
            return str_constants[clean]
        idx = len(str_constants) + 1
        global_name = f"@.str.{idx}"
        raw_bytes = clean.encode("utf-8") + b"\x00"
        length = len(raw_bytes)
        hex_content = "".join(
            c if (32 <= ord(c) < 127 and c not in ('\\', '"')) else f"\\{ord(c):02X}"
            for c in clean
        ) + "\\00"
        decl = f'{global_name} = private unnamed_addr constant [{length} x i8] c"{hex_content}", align 1'
        globals_list.append(decl)
        info = {"name": global_name, "len": length}
        str_constants[clean] = info
        return info

    def gen_expr(e):
        if not e:
            return "0", "i32"
        t = e.get("type")
        if t == "Num":
            val = e["value"]
            if isinstance(val, float) or "." in str(val):
                return str(float(val)), "double"
            return str(int(val)), "i32"
        if t == "Str":
            info = get_str_constant(e["value"])
            r = new_reg()
            lines.append(f"  {r} = getelementptr inbounds [{info['len']} x i8], [{info['len']} x i8]* {info['name']}, i32 0, i32 0")
            return r, "i8*"
        if t == "Id":
            name = e["name"]
            vtype = get_var_type(name)
            r = new_reg()
            lines.append(f"  {r} = load {vtype}, {vtype}* %{name}, align 4")
            return r, vtype
        if t == "Input":
            r = new_reg()
            temp_alloc = f"%__tmp_in_{reg_counter[0]}"
            lines.append(f"  {temp_alloc} = alloca i32, align 4")
            lines.append(f"  call i32 (i8*, ...) @__isoc99_scanf(i8* getelementptr inbounds ([3 x i8], [3 x i8]* @.str.scanf_int, i32 0, i32 0), i32* {temp_alloc})")
            lines.append(f"  {r} = load i32, i32* {temp_alloc}, align 4")
            return r, "i32"
        if t in ("BinOp", "Compare"):
            l_val, l_type = gen_expr(e["left"])
            r_val, r_type = gen_expr(e["right"])
            is_float = (l_type in ("float", "double") or r_type in ("float", "double"))
            op_type = "double" if is_float else "i32"

            op = e["op"]
            r = new_reg()
            if op == "+":
                instr = "fadd double" if is_float else "add nsw i32"
                lines.append(f"  {r} = {instr} {l_val}, {r_val}")
                return r, op_type
            elif op == "-":
                instr = "fsub double" if is_float else "sub nsw i32"
                lines.append(f"  {r} = {instr} {l_val}, {r_val}")
                return r, op_type
            elif op == "*":
                instr = "fmul double" if is_float else "mul nsw i32"
                lines.append(f"  {r} = {instr} {l_val}, {r_val}")
                return r, op_type
            elif op == "/":
                instr = "fdiv double" if is_float else "sdiv i32"
                lines.append(f"  {r} = {instr} {l_val}, {r_val}")
                return r, op_type
            elif op in ("==", "!=", "<", ">", "<=", ">="):
                cmp_map_int = {
                    "==": "eq", "!=": "ne", "<": "slt",
                    ">": "sgt", "<=": "sle", ">=": "sge"
                }
                cmp_map_float = {
                    "==": "oeq", "!=": "one", "<": "olt",
                    ">": "ogt", "<=": "ole", ">=": "oge"
                }
                if is_float:
                    pred = cmp_map_float.get(op, "oeq")
                    lines.append(f"  {r} = fcmp {pred} double {l_val}, {r_val}")
                else:
                    pred = cmp_map_int.get(op, "eq")
                    lines.append(f"  {r} = icmp {pred} i32 {l_val}, {r_val}")
                return r, "i1"
        return "0", "i32"

    # Step 1: Pre-collect variable declarations for stack allocation (alloca)
    allocated_vars = set()
    alloca_lines = []

    def find_decls(stmts):
        for s in stmts:
            if s["type"] == "VarDecl":
                name = s["name"]
                if name not in allocated_vars:
                    vtype = get_var_type(name)
                    alloca_lines.append(f"  %{name} = alloca {vtype}, align 4")
                    allocated_vars.add(name)
            elif s["type"] == "Assign":
                name = s["name"]
                if name not in allocated_vars:
                    vtype = get_var_type(name)
                    alloca_lines.append(f"  %{name} = alloca {vtype}, align 4")
                    allocated_vars.add(name)
            elif s["type"] == "If":
                find_decls(s.get("then", []))
                find_decls(s.get("else", []))
            elif s["type"] == "While":
                find_decls(s.get("body", []))

    find_decls(ast)

    # Step 2: Generate code for statements
    def walk(stmts):
        for s in stmts:
            stype = s["type"]
            line_no = s.get("line", "")
            if stype == "VarDecl":
                name = s["name"]
                vtype = get_var_type(name)
                lines.append(f"  ; line {line_no}: declaration of {name}")
                if s.get("expr") is not None:
                    val, _ = gen_expr(s["expr"])
                    lines.append(f"  store {vtype} {val}, {vtype}* %{name}, align 4")
            elif stype == "Assign":
                name = s["name"]
                vtype = get_var_type(name)
                lines.append(f"  ; line {line_no}: {name} = ...")
                val, _ = gen_expr(s["expr"])
                lines.append(f"  store {vtype} {val}, {vtype}* %{name}, align 4")
            elif stype == "Print":
                lines.append(f"  ; line {line_no}: print")
                args = s.get("args", [])
                # If first arg is a C-style format string with specifiers: printf("%d", sum)
                if len(args) > 1 and args[0].get("type") == "Str" and FORMAT_RE.search(clean_str(args[0].get("value", ""))):
                    fmt_info = get_str_constant(args[0]["value"])
                    fmt_ptr = new_reg()
                    lines.append(f"  {fmt_ptr} = getelementptr inbounds [{fmt_info['len']} x i8], [{fmt_info['len']} x i8]* {fmt_info['name']}, i32 0, i32 0")
                    call_args = [f"i8* {fmt_ptr}"]
                    for a in args[1:]:
                        val, atype = gen_expr(a)
                        call_args.append(f"{atype} {val}")
                    call_r = new_reg()
                    lines.append(f"  {call_r} = call i32 (i8*, ...) @printf({', '.join(call_args)})")
                else:
                    for arg in args:
                        val, atype = gen_expr(arg)
                        call_r = new_reg()
                        if atype == "i32":
                            lines.append(f"  {call_r} = call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @.str.int, i32 0, i32 0), i32 {val})")
                        elif atype in ("float", "double"):
                            lines.append(f"  {call_r} = call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @.str.float, i32 0, i32 0), double {val})")
                        elif atype == "i8*":
                            lines.append(f"  {call_r} = call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @.str.str, i32 0, i32 0), i8* {val})")
                        else:
                            lines.append(f"  {call_r} = call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @.str.int, i32 0, i32 0), i32 {val})")
            elif stype == "If":
                lines.append(f"  ; line {line_no}: if / else")
                cond_val, _ = gen_expr(s["cond"])
                lbl_then = new_label("if.then")
                lbl_else = new_label("if.else") if s.get("else") else None
                lbl_end = new_label("if.end")
                false_lbl = lbl_else if lbl_else else lbl_end

                lines.append(f"  br i1 {cond_val}, label %{lbl_then}, label %{false_lbl}")

                lines.append(f"{lbl_then}:")
                walk(s.get("then", []))
                lines.append(f"  br label %{lbl_end}")

                if lbl_else:
                    lines.append(f"{lbl_else}:")
                    walk(s.get("else", []))
                    lines.append(f"  br label %{lbl_end}")

                lines.append(f"{lbl_end}:")
            elif stype == "While":
                lines.append(f"  ; line {line_no}: while loop")
                lbl_cond = new_label("while.cond")
                lbl_body = new_label("while.body")
                lbl_end = new_label("while.end")

                lines.append(f"  br label %{lbl_cond}")
                lines.append(f"{lbl_cond}:")
                cond_val, _ = gen_expr(s["cond"])
                lines.append(f"  br i1 {cond_val}, label %{lbl_body}, label %{lbl_end}")

                lines.append(f"{lbl_body}:")
                walk(s.get("body", []))
                lines.append(f"  br label %{lbl_cond}")

                lines.append(f"{lbl_end}:")
            elif stype == "Return":
                lines.append(f"  ; line {line_no}: return")
                if s.get("expr"):
                    val, _ = gen_expr(s["expr"])
                    lines.append(f"  ret i32 {val}")
                else:
                    lines.append("  ret i32 0")

    walk(ast)

    # Ensure main ends with ret i32 0 if not terminated
    if not any(l.strip().startswith("ret ") for l in lines[-3:]):
        lines.append("  ret i32 0")

    # Assemble full LLVM module text
    module_header = [
        "; ModuleID = 'explainable_compiler_module'",
        f"; Source language: {lang.upper()}",
        'source_filename = "main"',
        'target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"',
        'target triple = "x86_64-pc-linux-gnu"',
        "",
        '; Standard format strings for output & input',
        '@.str.int = private unnamed_addr constant [4 x i8] c"%d\\0A\\00", align 1',
        '@.str.float = private unnamed_addr constant [4 x i8] c"%f\\0A\\00", align 1',
        '@.str.str = private unnamed_addr constant [4 x i8] c"%s\\0A\\00", align 1',
        '@.str.scanf_int = private unnamed_addr constant [3 x i8] c"%d\\00", align 1',
    ]

    if globals_list:
        module_header.append("; String literals")
        module_header.extend(globals_list)

    module_header.extend([
        "",
        "; External runtime declarations",
        "declare i32 @printf(i8*, ...)",
        "declare i32 @__isoc99_scanf(i8*, ...)",
        "",
        "; Main program entry point",
        "define i32 @main() {",
        "entry:",
    ])

    if alloca_lines:
        module_header.append("  ; Local stack allocations (Clang -O0 memory model)")
        module_header.extend(alloca_lines)
        module_header.append("")

    full_code = "\n".join(module_header + lines + ["}"])

    concepts = [
        {
            "title": "Static Single Assignment (SSA) Form",
            "desc": "Virtual registers like %1, %2, %3 are immutable: they are assigned exactly once upon creation. This prevents hidden side-effects and makes program analysis vastly simpler."
        },
        {
            "title": "Explicit Memory Model (alloca, load, store)",
            "desc": "At -O0, Clang and LLVM allocate local variables on the stack via 'alloca'. Variables are only accessed through explicit 'load' and 'store' instructions. The LLVM 'mem2reg' pass later elevates these into pure registers with phi-nodes."
        },
        {
            "title": "Strong Static Typing",
            "desc": "Every single instruction explicitly declares the bitwidth and type of its operands (e.g. i32 for 32-bit integers, i1 for booleans, double, i8*)."
        },
        {
            "title": "Basic Blocks & Explicit Branching",
            "desc": "Control flow is partitioned into contiguous basic blocks (entry, if.then, if.else, while.cond). Every basic block must end with an explicit terminator instruction ('br' or 'ret')."
        }
    ]

    return {
        "raw": full_code,
        "lineCount": len(full_code.splitlines()),
        "concepts": concepts,
    }
