"""python manage.py test formulas"""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .validators import validate_calc_expression, validate_latex


class LatexValidatorTests(SimpleTestCase):
    def test_good_latex_passes(self):
        for t in [r"E=mc^2", r"\frac{a}{b}", r"\sum_{i=1}^{n} x_i", r"\left|x\right|", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}", r"\det A"]:
            self.assertEqual(validate_latex(t), t)

    def test_unbalanced_brackets_rejected(self):
        with self.assertRaises(ValidationError):
            validate_latex(r"\frac{a}{b")

    def test_unsafe_commands_rejected(self):
        for t in [r"\href{http://x}{y}", r"\url{http://x}", r"\includegraphics{a}", r"\input{a}", r"\def\x{1}", "<script>alert(1)</script>", r"\htmlClass{a}{b}"]:
            with self.assertRaises(ValidationError, msg=t):
                validate_latex(t)

    def test_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            validate_latex("x" * 4001)

    def test_calc_expression(self):
        for ok in ["0.5*m*v^2", "pi*r^2", "sqrt(a^2+b^2)", ""]:
            validate_calc_expression(ok)
        for bad in ["import('x')", "evaluate(1)", "a; b", "a=1", "m*v`", "(a+b", "x[1]"]:
            with self.assertRaises(ValidationError, msg=bad):
                validate_calc_expression(bad)
