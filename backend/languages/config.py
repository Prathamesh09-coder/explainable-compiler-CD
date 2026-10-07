"""
Language configuration for the Explainable Compiler.

Each entry describes the *educational subset* supported for that language:
declarations, arithmetic, comparisons, print, if/else, while.
Nothing here claims full compiler-grade support for the real language.
"""

LANGS = {
    "c": {
        "name": "C",
        "style": "brace",
        "keywords": ["int", "float", "double", "char", "void", "if", "else",
                     "while", "for", "return", "printf", "scanf", "include"],
        "sample": (
            "#include <stdio.h>\n\n"
            "int main() {\n"
            "    int a = 10;\n"
            "    int b = 20;\n"
            "    int sum = a + b;\n"
            '    printf("%d", sum);\n'
            "    return 0;\n"
            "}"
        ),
        "pipeline": ["preprocess", "lexical", "syntax", "expressions", "semantic",
                     "symtab", "ir", "optimize", "target", "execute", "summary"],
    },
    "cpp": {
        "name": "C++",
        "style": "brace",
        "keywords": ["int", "float", "double", "char", "void", "if", "else",
                     "while", "for", "return", "cout", "cin", "include",
                     "using", "namespace", "std"],
        "sample": (
            "#include <iostream>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    int a = 10;\n"
            "    int b = 20;\n"
            "    int sum = a + b;\n"
            "    cout << sum;\n"
            "    return 0;\n"
            "}"
        ),
        "pipeline": ["preprocess", "lexical", "syntax", "expressions", "semantic",
                     "symtab", "ir", "optimize", "target", "execute", "summary"],
    },
    "java": {
        "name": "Java",
        "style": "brace",
        "keywords": ["int", "float", "double", "void", "if", "else", "while",
                     "for", "return", "class", "public", "static", "String"],
        "sample": (
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        int a = 10;\n"
            "        int b = 20;\n"
            "        int sum = a + b;\n"
            "        System.out.println(sum);\n"
            "    }\n"
            "}"
        ),
        "pipeline": ["lexical", "syntax", "expressions", "semantic", "symtab",
                     "ir", "optimize", "target", "execute", "summary"],
    },
    "python": {
        "name": "Python",
        "style": "indent",
        "keywords": ["if", "else", "while", "for", "def", "return", "print",
                     "input", "True", "False", "None"],
        "sample": "a = 10\nb = 20\nsum = a + b\nprint(sum)",
        "pipeline": ["lexical", "syntax", "expressions", "semantic", "symtab",
                     "ir", "optimize", "target", "execute", "summary"],
    },
}

MAX_CODE_LENGTH = 20000
MAX_INPUT_LENGTH = 4000
