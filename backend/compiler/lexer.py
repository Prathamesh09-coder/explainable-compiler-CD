"""
Phase: Preprocessing + Lexical Analysis.

preprocess()  -> strips C/C++ preprocessor directives (#include, #define) out
                 of the source before real compilation, and records them so
                 the UI can explain what they do.
tokenize()    -> classic hand-written scanner: turns a character stream into
                 a token stream (lexemes + token type + category + line).
"""
import re

OP_RE = re.compile(r'^(==|!=|<=|>=|<<|>>|&&|\|\||[+\-*/=<>!])')
STRING_RE = re.compile(r'^"([^"]*)"')
NUMBER_RE = re.compile(r'^[0-9]+(\.[0-9]+)?')
IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*')
SEP_RE = re.compile(r'^[;(){}\[\],:\.]')


def preprocess(src: str, lang: str):
    if lang not in ("c", "cpp"):
        return {
            "directives": [],
            "body": src,
            "note": (
                "This phase is not applicable in the same form to this language. "
                "Python and Java have no textual preprocessor: Java uses import/package "
                "declarations resolved by the compiler, and Python uses import statements "
                "resolved at run time -- neither performs blind textual substitution before "
                "compilation."
            ),
        }
    directives = []
    kept = []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("#include"):
            directives.append({
                "type": "include", "text": t,
                "explain": "Tells the preprocessor to paste the contents of a header file "
                           "(declarations for library functions) here, before compilation proper begins.",
            })
            kept.append("")  # keep line numbers aligned with the original source
        elif t.startswith("#define"):
            directives.append({
                "type": "define", "text": t,
                "explain": "Defines a macro: the preprocessor textually substitutes every later "
                           "occurrence of the macro name with its replacement text.",
            })
            kept.append("")  # keep line numbers aligned with the original source
        else:
            kept.append(line)
    return {"directives": directives, "body": "\n".join(kept), "note": None}


def tokenize(src: str, lang: str, keywords):
    kw = set(keywords)
    tokens = []
    for li, line in enumerate(src.split("\n")):
        col = 0
        while col < len(line):
            rest = line[col:]
            start_col = col + 1  # 1-indexed, for pointing at the exact character in the UI
            if rest[0].isspace():
                col += 1
                continue
            if rest.startswith("//"):
                tokens.append({"t": "COMMENT", "cat": "Comment", "v": rest, "line": li + 1, "col": start_col})
                break
            if rest.startswith("#"):
                tokens.append({"t": "PREPROC", "cat": "Preprocessor directive", "v": rest, "line": li + 1, "col": start_col})
                break
            m = STRING_RE.match(rest)
            if m:
                tokens.append({"t": "STRING_LITERAL", "cat": "String", "v": m.group(0), "line": li + 1, "col": start_col})
                col += len(m.group(0)); continue
            m = NUMBER_RE.match(rest)
            if m:
                tt = "FLOAT_LITERAL" if "." in m.group(0) else "INTEGER_LITERAL"
                tokens.append({"t": tt, "cat": "Literal", "v": m.group(0), "line": li + 1, "col": start_col})
                col += len(m.group(0)); continue
            m = IDENT_RE.match(rest)
            if m:
                word = m.group(0)
                if word in kw:
                    tokens.append({"t": word.upper(), "cat": "Keyword", "v": word, "line": li + 1, "col": start_col})
                else:
                    tokens.append({"t": "IDENTIFIER", "cat": "Identifier", "v": word, "line": li + 1, "col": start_col})
                col += len(word); continue
            m = OP_RE.match(rest)
            if m:
                tokens.append({"t": "OPERATOR", "cat": "Operator", "v": m.group(0), "line": li + 1, "col": start_col})
                col += len(m.group(0)); continue
            m = SEP_RE.match(rest)
            if m:
                tokens.append({"t": "SEPARATOR", "cat": "Separator", "v": m.group(0), "line": li + 1, "col": start_col})
                col += 1; continue
            tokens.append({"t": "ILLEGAL", "cat": "Illegal character", "v": rest[0], "line": li + 1, "col": start_col, "error": True})
            col += 1
    return tokens


def extract_body(src: str, lang: str):
    """Strip the main()/class boilerplate so the parser only sees the statement body."""
    if lang == "python":
        return src, None
    idx = src.find("main(")
    if idx == -1:
        return src, "No main() found -- analyzing whole source as the statement body."
    brace_start = src.find("{", idx)
    if brace_start == -1:
        return src, None
    depth = 0
    i = brace_start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    # Pad with the same number of blank lines that the stripped prefix contained,
    # so line numbers inside the extracted body still match the ORIGINAL source
    # the user typed/uploaded -- otherwise every later line number (tokens, AST,
    # error messages) is silently off by however many lines precede main().
    prefix_newlines = src[:brace_start + 1].count("\n")
    inner = ("\n" * prefix_newlines) + src[brace_start + 1:i]
    note = ("The surrounding class/main() declaration is standard Java boilerplate; this analyzer "
            "focuses on the statements inside main()." if lang == "java" else
            "The surrounding main() function signature is boilerplate; this analyzer focuses on the "
            "statements inside its body.")
    return inner, note
