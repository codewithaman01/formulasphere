"""Checks shared by the staff panel and the student submission form."""
import re
from django.core.exceptions import ValidationError

_BAD_LATEX = re.compile(r"\\(href|url|includegraphics|input|include|write|openout|read|catcode|def|edef|gdef|newcommand|"
                        r"html(Class|Id|Style|Data)|immediate)\b|<\s*/?\s*(script|iframe|img|svg|style)", re.I)


def validate_latex(value):
    """Rejects empty / unbalanced / unsafe LaTeX. KaTeX is also run with trust:false on the site."""
    v = (value or "").strip()
    if not v:
        return v
    if len(v) > 4000:
        raise ValidationError("This LaTeX is too long (limit 4000 characters).")
    if _BAD_LATEX.search(v):
        raise ValidationError("This LaTeX uses a command that is not allowed (links, files, macro definitions or HTML).")
    depth = 0
    for i, ch in enumerate(v):
        if ch in "{}" and (i == 0 or v[i - 1] != "\\"):
            depth += 1 if ch == "{" else -1
            if depth < 0:
                break
    if depth != 0:
        raise ValidationError("Curly brackets { } are not balanced. Check the preview below the box.")
    return v


_CALC_OK = re.compile(r"^[A-Za-z0-9_+\-*/^().,\s]*$")
_CALC_BAD = re.compile(r"\b(import|evaluate|parse|compile|simplify|derivative|createUnit|reviver|help|config|typed|chain|resolve)\b")


def validate_calc_expression(value):
    """The calculator expression is run in the visitor's browser with math.js. Keep it to plain maths."""
    v = (value or "").strip()
    if not v:
        return v
    if not _CALC_OK.match(v) or _CALC_BAD.search(v):
        raise ValidationError("Use only numbers, names, + - * / ^ ( ) and functions such as sqrt(x) or sin(x). Example: 0.5*m*v^2")
    if v.count("(") != v.count(")"):
        raise ValidationError("The round brackets ( ) are not balanced.")
    return v
