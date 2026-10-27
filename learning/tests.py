from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import StaffAssignment, StaffRole
from formulas.models import Formula
from taxonomy import seeding as tax
from taxonomy.models import Grade, Subject, Topic
from .models import ClassRegistration, Course, Enrollment, LiveClass, TuitionEnquiry, TuitionOffer

User = get_user_model()


def user(name, **kw):
    return User.objects.create_user(name, f"{name}@example.com", "pw-Str0ng-pass!9", **kw)


class LearningBase(TestCase):
    def setUp(self):
        cache.clear()
        tax.load_levels(); tax.load_grades(); tax.load_subjects()
        self.maths = Subject.objects.get(name="Mathematics")
        self.g9 = Grade.objects.get(slug="class-9")
        self.free = Course.objects.create(title="Free Course", slug="free-course", subject=self.maths, is_published=True)
        self.free.grades.add(self.g9)
        self.paid = Course.objects.create(title="Paid Course", slug="paid-course", subject=self.maths, price=500, is_published=True)
        self.draft = Course.objects.create(title="Draft Course", slug="draft-course", subject=self.maths)
        self.stu = user("stu")

    def live(self, **kw):
        d = dict(title="Algebra live", slug="algebra-live", subject=self.maths, starts_at=timezone.now() + timedelta(days=1),
                 join_url="https://meet.example.com/abc", is_published=True)
        d.update(kw)
        return LiveClass.objects.create(**d)


class CourseTests(LearningBase):
    def test_list_shows_only_published_and_filters_by_grade(self):
        r = self.client.get("/courses/")
        self.assertContains(r, "Free Course"); self.assertNotContains(r, "Draft Course")
        r = self.client.get("/courses/?grade=class-9")
        self.assertContains(r, "Free Course"); self.assertNotContains(r, "Paid Course")
        self.assertEqual(self.client.get("/courses/draft-course/").status_code, 404)

    def test_anonymous_must_sign_in_to_enrol(self):
        r = self.client.post("/courses/free-course/enroll/")
        self.assertEqual(r.status_code, 302); self.assertIn("login", r["Location"])

    def test_free_course_activates_and_paid_course_waits(self):
        self.client.force_login(self.stu)
        self.client.post("/courses/free-course/enroll/")
        self.client.post("/courses/paid-course/enroll/")
        self.assertEqual(Enrollment.objects.get(course=self.free).status, "active")
        self.assertEqual(Enrollment.objects.get(course=self.paid).status, "pending")
        self.assertContains(self.client.get("/courses/paid-course/"), "Waiting for payment")
        self.client.post("/courses/free-course/enroll/")             # twice is harmless
        self.assertEqual(Enrollment.objects.filter(user=self.stu).count(), 2)

    def test_my_learning_lists_enrolments(self):
        self.client.force_login(self.stu)
        self.client.post("/courses/free-course/enroll/")
        self.assertContains(self.client.get("/my-learning/"), "Free Course")


class LiveClassTests(LearningBase):
    def test_register_and_link_is_hidden_until_shortly_before(self):
        lc = self.live()
        self.client.force_login(self.stu)
        self.client.post("/live/algebra-live/register/")
        self.assertTrue(ClassRegistration.objects.filter(user=self.stu, live_class=lc).exists())
        self.assertNotContains(self.client.get("/live/algebra-live/"), "meet.example.com")
        lc.starts_at = timezone.now() + timedelta(minutes=5); lc.save()
        self.assertContains(self.client.get("/live/algebra-live/"), "meet.example.com")

    def test_link_never_shown_to_unregistered_people(self):
        self.live(starts_at=timezone.now() + timedelta(minutes=2))
        self.assertNotContains(self.client.get("/live/algebra-live/"), "meet.example.com")
        self.client.force_login(self.stu)
        self.assertNotContains(self.client.get("/live/algebra-live/"), "meet.example.com")

    def test_join_window_comes_from_settings(self):
        lc = self.live(starts_at=timezone.now() + timedelta(minutes=40))
        self.assertFalse(lc.join_open())
        with override_settings(LIVE_JOIN_EARLY_MINUTES=60):
            self.assertTrue(lc.join_open())

    def test_capacity_is_enforced_and_cancelling_frees_a_seat(self):
        self.live(capacity=1)
        other = user("other")
        self.client.force_login(other); self.client.post("/live/algebra-live/register/")
        self.client.force_login(self.stu); r = self.client.post("/live/algebra-live/register/", follow=True)
        self.assertContains(r, "full")
        self.assertEqual(ClassRegistration.objects.count(), 1)
        self.client.force_login(other); self.client.post("/live/algebra-live/cancel/")
        self.client.force_login(self.stu); self.client.post("/live/algebra-live/register/")
        self.assertTrue(ClassRegistration.objects.filter(user=self.stu).exists())

    def test_course_students_get_the_link_without_registering(self):
        lc = self.live(course=self.free, starts_at=timezone.now() + timedelta(minutes=3))
        Enrollment.objects.create(user=self.stu, course=self.free, status="active")
        self.client.force_login(self.stu)
        self.assertContains(self.client.get("/live/algebra-live/"), "meet.example.com")
        pending = user("pend"); Enrollment.objects.create(user=pending, course=self.free, status="pending")
        self.client.force_login(pending)
        self.assertNotContains(self.client.get("/live/algebra-live/"), "meet.example.com")

    def test_recording_shown_to_registered_after_the_class(self):
        lc = self.live(starts_at=timezone.now() - timedelta(hours=3), recording_url="https://video.example.com/r1")
        ClassRegistration.objects.create(user=self.stu, live_class=lc)
        self.client.force_login(self.stu)
        self.assertContains(self.client.get("/live/algebra-live/"), "video.example.com")
        self.assertNotContains(self.client.get("/live/algebra-live/"), "meet.example.com")

    def test_cannot_register_after_it_finished(self):
        self.live(starts_at=timezone.now() - timedelta(hours=3))
        self.client.force_login(self.stu)
        self.client.post("/live/algebra-live/register/")
        self.assertEqual(ClassRegistration.objects.count(), 0)

    def test_list_separates_upcoming_and_hides_unpublished(self):
        self.live(); self.live(title="Hidden", slug="hidden", is_published=False)
        r = self.client.get("/live/")
        self.assertContains(r, "Algebra live"); self.assertNotContains(r, "Hidden")


class TuitionTests(LearningBase):
    def post(self, **kw):
        d = {"name": "Parent", "phone": "9999999999", "grade": "class-9", "message": "Need maths help"}
        d.update(kw)
        return self.client.post("/tuition/", d)

    def test_enquiry_is_saved(self):
        offer = TuitionOffer.objects.create(title="Maths", slug="maths", subject=self.maths, is_published=True)
        self.post(offer=offer.pk)
        q = TuitionEnquiry.objects.get()
        self.assertEqual((q.name, q.grade, q.status, q.offer_id), ("Parent", "class-9", "new", offer.pk))

    def test_needs_a_name_and_a_way_to_reach_them_and_a_real_grade(self):
        r = self.post(name="", phone="")
        self.assertContains(r, "Please enter your name"); self.assertContains(r, "phone number or an email")
        self.assertContains(self.post(grade="class-99"), "choose a grade")
        self.assertEqual(TuitionEnquiry.objects.count(), 0)

    def test_bots_and_floods_are_stopped(self):
        self.post(website="http://spam")
        self.assertEqual(TuitionEnquiry.objects.count(), 0)
        for _ in range(7):
            self.post()
        self.assertEqual(TuitionEnquiry.objects.count(), 5)

    def test_only_published_offers_listed(self):
        TuitionOffer.objects.create(title="Shown", slug="shown", subject=self.maths, is_published=True)
        TuitionOffer.objects.create(title="Secret", slug="secret", subject=self.maths)
        r = self.client.get("/tuition/")
        self.assertContains(r, "Shown"); self.assertNotContains(r, "Secret")


class PanelLearningTests(LearningBase):
    def staff(self, name, codes):
        u = user(name)
        StaffAssignment.objects.create(user=u, role=StaffRole.objects.create(name="R" + name, access=codes))
        return u

    def test_creating_a_course_and_live_class_in_the_panel(self):
        self.client.force_login(user("root", is_superuser=True, is_staff=True))
        r = self.client.post("/panel/c/courses/new/", {"title": "New course", "slug": "", "subject": self.maths.pk, "grades": [self.g9.pk],
                                                       "mode": "live", "price": "0", "is_published": "on", "sort_order": 0})
        c = Course.objects.get(title="New course")
        self.assertEqual((c.slug, list(c.grades.all())), ("new-course", [self.g9]))
        self.client.post("/panel/c/live_classes/new/", {"title": "Class 1", "slug": "", "subject": self.maths.pk, "grades": [self.g9.pk],
                                                         "starts_at": "2030-01-05T17:30", "duration_minutes": 45, "is_published": "on"})
        lc = LiveClass.objects.get(title="Class 1")
        self.assertEqual((lc.duration_minutes, lc.starts_at.year), (45, 2030))

    def test_staff_confirms_a_payment_by_activating_the_enrollment(self):
        e = Enrollment.objects.create(user=self.stu, course=self.paid)
        mgr = self.staff("mgr", ["enrollments.view", "enrollments.change"])
        self.client.force_login(mgr)
        self.assertContains(self.client.get("/panel/c/enrollments/"), "stu")
        self.client.post(f"/panel/c/enrollments/{e.pk}/edit/", {"user": self.stu.pk, "course": self.paid.pk, "status": "active", "note": "UPI ref 123"})
        e.refresh_from_db()
        self.assertEqual((e.status, e.note), ("active", "UPI ref 123"))

    def test_enquiries_can_be_followed_up(self):
        q = TuitionEnquiry.objects.create(name="Parent", phone="999")
        self.client.force_login(self.staff("tutor", ["enquiries.view", "enquiries.change"]))
        self.assertContains(self.client.get("/panel/c/enquiries/"), "Parent")
        self.client.post(f"/panel/c/enquiries/{q.pk}/edit/", {"name": "Parent", "phone": "999", "email": "", "grade": "", "subject_wanted": "",
                                                              "message": "", "status": "contacted", "staff_note": "Called on Monday"})
        q.refresh_from_db()
        self.assertEqual((q.status, q.staff_note), ("contacted", "Called on Monday"))

    def test_staff_without_the_permission_are_refused(self):
        self.client.force_login(self.staff("nobody", ["formulas.view"]))
        self.assertEqual(self.client.get("/panel/c/courses/").status_code, 403)
        self.assertEqual(self.client.get("/panel/c/enquiries/").status_code, 403)

    def test_subject_in_use_by_a_course_cannot_be_deleted(self):
        self.client.force_login(user("root", is_superuser=True, is_staff=True))
        self.client.post(f"/panel/c/subjects/{self.maths.pk}/delete/")
        self.assertTrue(Subject.objects.filter(pk=self.maths.pk).exists())


class SeedAndExplanationTests(LearningBase):
    def test_seed_learning_makes_unpublished_drafts_and_is_repeatable(self):
        call_command("seed_content", stdout=StringIO())
        call_command("seed_learning", stdout=StringIO())
        n, t = Course.objects.count(), TuitionOffer.objects.count()
        self.assertGreaterEqual(n, 10); self.assertGreaterEqual(t, 4)
        self.assertFalse(Course.objects.filter(is_published=True, slug__in=["class-9-mathematics", "python-programming-basics"]).exists())
        c = Course.objects.get(slug="class-9-mathematics")
        self.assertEqual([g.slug for g in c.grades.all()], ["class-9"])
        self.assertGreater(c.topics.count(), 1); self.assertGreater(len(c.lessons), 3)
        call_command("seed_learning", stdout=StringIO())
        self.assertEqual((Course.objects.count(), TuitionOffer.objects.count()), (n, t))

    def test_explanations_load_once_and_never_overwrite_edits(self):
        call_command("seed_content", stdout=StringIO())
        f = Formula.objects.get(title="Quadratic formula")
        self.assertIn("discriminant", f.detailed_explanation)
        self.assertTrue(f.examples.filter(title="Solve a quadratic").exists())
        t = Topic.objects.get(subject__name="Mathematics", name="Mensuration")
        self.assertIn("perimeter", t.explanation)
        f.detailed_explanation = "My own words"; f.save()
        t.explanation = "Mine"; t.save()
        n = f.examples.count()
        call_command("seed_content", stdout=StringIO())
        f.refresh_from_db(); t.refresh_from_db()
        self.assertEqual((f.detailed_explanation, t.explanation, f.examples.count()), ("My own words", "Mine", n))

    def test_topic_page_shows_the_explanation(self):
        call_command("seed_content", stdout=StringIO())
        u = user("root", is_superuser=True); self.client.force_login(u)
        r = self.client.get("/subjects/mathematics/topics/mensuration/") if False else None
        from django.urls import reverse
        r = self.client.get(reverse("topic", args=["mathematics", "mensuration"]))
        self.assertContains(r, "About this topic"); self.assertContains(r, "measurement of shapes")
