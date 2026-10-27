"""python manage.py test web   (needs the MongoDB settings in .env)"""
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import Profile
from accounts.tests import make_student
from formulas.models import (Bookmark, Example, Formula, FormulaView, PracticeAttempt, SearchLog, Status)
from taxonomy.models import AcademicLevel, Subject
from .models import StaticPage

PW = "pw-Str0ng-pass"


def make_formula(slug="ohm", title="Ohm's law", status=Status.PUBLISHED, tier="basic", **kw):
    f = Formula.objects.create(title=title, slug=slug, latex="V=IR", short_explanation="Voltage equals current times resistance.",
                               status=status, access_tier=tier, **kw)
    f.subjects.add(Subject.objects.get_or_create(slug="physics", defaults=dict(name="Physics", is_published=True))[0])
    f.levels.add(AcademicLevel.objects.get_or_create(slug="school", defaults=dict(name="School"))[0])
    return f


def login(user):
    c = Client(); assert c.login(username=user.username, password=PW); return c


class ProtectionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.f = make_formula()

    def test_student_page_is_protected_and_has_no_copy_latex(self):
        html = login(make_student("s1")).get("/formulas/ohm/").content.decode()
        self.assertIn('data-protect="1"', html)
        self.assertIn("s1", html)                       # watermark name
        self.assertNotIn("Copy LaTeX", html)

    def test_staff_page_is_not_protected(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_superuser("boss", "b@example.com", PW)
        c = Client(); c.login(username="boss", password=PW)
        html = c.get("/formulas/ohm/").content.decode()
        self.assertNotIn('data-protect="1"', html)
        self.assertIn("Copy LaTeX", html)

    def test_anonymous_goes_to_login(self):
        self.assertEqual(Client().get("/formulas/ohm/").status_code, 302)

    @override_settings(VIEW_LIMIT_PER_HOUR=2)
    def test_view_limit(self):
        c = login(make_student("fast"))
        self.assertEqual([c.get("/formulas/ohm/").status_code for _ in range(3)], [200, 200, 429])

    def test_views_are_logged_once_per_ten_minutes(self):
        c = login(make_student("log")); c.get("/formulas/ohm/"); c.get("/formulas/ohm/")
        self.assertEqual(FormulaView.objects.count(), 1)

    def test_trial_user_cannot_open_premium_formula(self):
        make_formula("premium-one", "Premium one", tier="premium")
        r = login(make_student("tri")).get("/formulas/premium-one/")
        self.assertEqual(r.status_code, 302); self.assertIn("/premium/", r["Location"])


class SavedAndPracticeTests(TestCase):
    def setUp(self):
        cache.clear(); self.f = make_formula(); self.u = make_student("pat"); self.c = login(self.u)

    def test_bookmark_toggle(self):
        self.c.post("/formulas/ohm/save/")
        self.assertEqual(Bookmark.objects.count(), 1)
        self.assertIn("Ohm", self.c.get("/saved/").content.decode())
        self.c.post("/formulas/ohm/save/")
        self.assertEqual(Bookmark.objects.count(), 0)

    def test_history_lists_viewed(self):
        self.c.get("/formulas/ohm/")
        self.assertIn("Ohm", self.c.get("/history/").content.decode())

    def test_practice_flow(self):
        ex = Example.objects.create(formula=self.f, title="Find V", problem="I=2 A, R=3 ohm. Find V.", solution="V=IR=6", result="6", units="V")
        self.assertIn("Find V", self.c.get("/practice/").content.decode())
        self.c.post(f"/practice/{ex.pk}/answer/", {"got_it": "1"})
        a = PracticeAttempt.objects.get(); self.assertTrue(a.got_it)
        self.assertIn("1 of 1", self.c.get("/practice/").content.decode())


class SubmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sub = Subject.objects.create(slug="physics", name="Physics", is_published=True)
        self.lvl = AcademicLevel.objects.create(slug="school", name="School")
        self.u = make_student("writer"); self.c = login(self.u)
        self.data = {"title": "Kinetic energy", "latex": r"K=\frac{1}{2}mv^2", "short_explanation": "Energy of motion.",
                     "detailed_explanation": "", "subjects": [self.sub.pk], "levels": [self.lvl.pk], "difficulty": "beginner", "keywords": ""}

    def test_submit_creates_submitted_formula(self):
        r = self.c.post("/submit/", self.data)
        self.assertEqual(r.status_code, 302)
        f = Formula.objects.get(); self.assertEqual((f.status, f.created_by), (Status.SUBMITTED, self.u))
        self.assertFalse(f.is_demo); self.assertEqual(f.revisions.count(), 1)
        self.assertIn("Kinetic energy", self.c.get("/my-submissions/").content.decode())

    def test_unsafe_latex_rejected(self):
        r = self.c.post("/submit/", {**self.data, "latex": r"\href{http://evil}{x}"})
        self.assertEqual(r.status_code, 200); self.assertEqual(Formula.objects.count(), 0)

    @override_settings(SUBMISSIONS_PER_DAY=2)
    def test_daily_limit(self):
        for i in range(2):
            self.c.post("/submit/", {**self.data, "title": f"T{i}"})
        self.c.post("/submit/", {**self.data, "title": "T3"})
        self.assertEqual(Formula.objects.count(), 2)

    def test_cannot_edit_someone_elses_or_a_submitted_formula(self):
        self.c.post("/submit/", self.data)
        f = Formula.objects.get()
        self.assertEqual(self.c.get(f"/submit/{f.pk}/").status_code, 404)     # already submitted: waiting for review
        f.status = Status.NEEDS_CORRECTION; f.save()
        self.assertEqual(self.c.get(f"/submit/{f.pk}/").status_code, 200)
        self.assertEqual(login(make_student("other")).get(f"/submit/{f.pk}/").status_code, 404)
        r = self.c.post(f"/submit/{f.pk}/", {**self.data, "title": "Kinetic energy v2"})
        f.refresh_from_db(); self.assertEqual((f.title, f.status), ("Kinetic energy v2", Status.SUBMITTED))


class SearchSeoPagesTests(TestCase):
    def setUp(self):
        cache.clear(); make_formula()
        # MongoDB has no rollback between tests, so the pages the migration added are gone: add them again
        from web.default_pages import PAGES
        for p in PAGES:
            StaticPage.objects.get_or_create(slug=p["slug"], defaults=dict(
                title=p["title"], body=p["body"], sort_order=p["sort_order"], show_in_footer=True, is_published=True))

    def test_zero_result_search_is_logged(self):
        Client().get("/explore/?q=zzzzqqqq")
        s = SearchLog.objects.get(); self.assertEqual((s.query, s.result_count), ("zzzzqqqq", 0))

    def test_sitemap_and_robots(self):
        r = Client().get("/sitemap.xml"); self.assertEqual(r.status_code, 200)
        self.assertIn(b"/explore/", r.content); self.assertNotIn(b"/formulas/", r.content)
        t = Client().get("/robots.txt").content.decode()
        self.assertIn("Disallow: /panel/", t); self.assertIn("sitemap.xml", t)

    def test_default_footer_pages_exist_and_render(self):
        self.assertTrue(StaticPage.objects.filter(slug="privacy").exists())
        r = Client().get("/p/privacy/"); self.assertEqual(r.status_code, 200)
        self.assertIn("Privacy", r.content.decode())
        self.assertIn("/p/terms/", Client().get("/").content.decode())     # footer link

    def test_unpublished_page_is_404(self):
        StaticPage.objects.filter(slug="terms").update(is_published=False)
        self.assertEqual(Client().get("/p/terms/").status_code, 404)

    def test_calculator_appears_when_expression_set(self):
        make_formula("ke", "Kinetic energy", calc_expression="0.5*m*v^2")
        html = login(make_student("calc")).get("/formulas/ke/").content.decode()
        self.assertIn('id="calc"', html); self.assertIn("mathjs", html)
        self.assertNotIn('id="calc"', login(make_student("calc2")).get("/formulas/ohm/").content.decode())


class DashboardTests(TestCase):
    def test_stats_show_for_owner(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_superuser("boss", "b@example.com", PW)
        make_student("a"); SearchLog.objects.create(query="missing thing", result_count=0)
        c = Client(); c.login(username="boss", password=PW)
        html = c.get("/panel/").content.decode()
        self.assertIn("Business at a glance", html); self.assertIn("missing thing", html)
