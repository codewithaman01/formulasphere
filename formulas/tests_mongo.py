"""python manage.py test formulas.tests_mongo  -- search, many-to-many batch loading and list fields on MongoDB"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import AccountType, StaffRole
from config.prefetch import prefetch
from taxonomy.models import AcademicLevel, Grade, Subject, Topic
from .models import Formula, Status
from .search import search_formulas


def make(title, slug, short="", keywords="", plain="", subjects=(), levels=(), status=Status.PUBLISHED):
    f = Formula.objects.create(title=title, slug=slug, latex="x", short_explanation=short or title, keywords=keywords,
                               plain_text=plain, status=status, published_at=timezone.now())
    f.subjects.add(*subjects)
    f.levels.add(*levels)
    return f


class SearchTests(TestCase):
    def setUp(self):
        self.maths = Subject.objects.create(name="Maths", slug="maths", is_published=True)
        self.phys = Subject.objects.create(name="Physics", slug="physics", is_published=True)
        self.lvl = AcademicLevel.objects.create(name="School", slug="school")
        make("Area of a circle", "circle", keywords="geometry, circle", subjects=[self.maths], levels=[self.lvl])
        make("Kinetic energy", "ke", short="Energy of motion of a moving body", subjects=[self.phys], levels=[self.lvl])
        make("Circular motion", "cm", short="Motion along a circle", subjects=[self.phys], levels=[self.lvl])
        make("Hidden draft", "draft", keywords="circle", status=Status.DRAFT, subjects=[self.maths], levels=[self.lvl])

    def slugs(self, **kw):
        return [f.slug for f in search_formulas(**kw)]

    def test_only_published_and_case_insensitive(self):
        self.assertEqual(sorted(self.slugs(q="CIRCLE")), ["circle", "cm"])         # the draft is never found

    def test_title_match_ranks_above_explanation_match(self):
        self.assertEqual(self.slugs(q="circle")[0], "circle")                       # title + keyword beat short explanation

    def test_every_word_must_match(self):
        self.assertEqual(self.slugs(q="motion circle"), ["cm"])
        self.assertEqual(self.slugs(q="circle zzzz"), [])

    def test_filters_and_sorting(self):
        self.assertEqual(self.slugs(subject="physics", sort="title"), ["cm", "ke"])
        self.assertEqual(self.slugs(subject="maths"), ["circle"])
        self.assertEqual(self.slugs(level="school", sort="title"), ["circle", "cm", "ke"])
        self.assertEqual(len(self.slugs(q="")), 3)

    def test_no_duplicates_when_formula_has_two_subjects(self):
        f = Formula.objects.get(slug="circle"); f.subjects.add(self.phys)
        self.assertEqual(self.slugs(level="school").count("circle"), 1)


class PrefetchTests(TestCase):
    def test_many_to_many_is_loaded_in_bulk_and_in_default_order(self):
        s1 = Subject.objects.create(name="B subject", slug="b", sort_order=2)
        s2 = Subject.objects.create(name="A subject", slug="a", sort_order=1)
        lvl = AcademicLevel.objects.create(name="School", slug="school")
        f1 = make("One", "one", subjects=[s1, s2], levels=[lvl]); f2 = make("Two", "two", subjects=[s1], levels=[lvl])
        make("Three", "three")
        items = prefetch(list(Formula.objects.order_by("title")), "subjects", "levels")
        with self.assertNumQueries(0):
            got = {f.slug: ([s.slug for s in f.subjects.all()], [l.slug for l in f.levels.all()]) for f in items}
        self.assertEqual(got["one"], (["a", "b"], ["school"]))                      # Subject ordering: sort_order
        self.assertEqual(got["two"], (["b"], ["school"]))
        self.assertEqual(got["three"], ([], []))

    def test_nested_many_to_many_then_foreign_key(self):
        from learning.models import Course
        subj = Subject.objects.create(name="Maths", slug="maths")
        topic = Topic.objects.create(name="Circles", slug="circles", subject=subj)
        c = Course.objects.create(title="C", slug="c", subject=subj); c.topics.add(topic)
        c = prefetch([Course.objects.get(pk=c.pk)], "topics__subject")[0]
        with self.assertNumQueries(0):
            self.assertEqual([t.subject.name for t in c.topics.all()], ["Maths"])

    def test_empty_input(self):
        self.assertEqual(prefetch([], "subjects"), [])


class ListFieldTests(TestCase):
    def test_grade_usage_finds_slug_inside_list_fields(self):
        lvl = AcademicLevel.objects.create(name="School", slug="school")
        g = Grade.objects.create(name="Class 9", slug="class-9", level=lvl, number=9)
        AccountType.objects.create(name="Teacher", slug="teacher", allowed_grades=["class-9", "class-10"])
        AccountType.objects.create(name="Other", slug="other", allowed_grades=["class-12"])
        StaffRole.objects.create(name="Editor", grades=["class-9"], access=["formulas.create"])
        self.assertEqual(g.usage(), {"account types": 1, "roles": 1})

    def test_lists_round_trip(self):
        r = StaffRole.objects.create(name="R", access=["a.b", "c.d"])
        self.assertEqual(StaffRole.objects.get(pk=r.pk).access, ["a.b", "c.d"])
        self.assertTrue(StaffRole.objects.get(pk=r.pk).has("c.d"))
