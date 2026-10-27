"""Run with:  python manage.py test panel   (needs the MongoDB settings in .env)"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts import totp
from accounts.models import AuditLog, Profile, StaffAssignment, StaffRole, TOTPDevice
from accounts.permissions import ACCESS, PAGES
from formulas.models import Formula
from taxonomy.models import AcademicLevel, Grade, Subject
from taxonomy import seeding as tax

User = get_user_model()


def make_user(name, **kw):
    return User.objects.create_user(name, f"{name}@example.com", "pw-Str0ng-pass", **kw)


class PanelAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.phys = Subject.objects.create(name="Physics", slug="physics")
        self.chem = Subject.objects.create(name="Chemistry", slug="chemistry")
        self.reviewer = StaffRole.objects.create(name="Reviewer", access=["formulas.review"])
        self.f_phys = Formula.objects.create(title="Ohm", slug="ohm", latex="V=IR", short_explanation="x")
        self.f_phys.subjects.add(self.phys)
        self.f_chem = Formula.objects.create(title="Mole", slug="mole", latex="n=m/M", short_explanation="x")
        self.f_chem.subjects.add(self.chem)

    def login(self, name):
        return self.client.post("/login/", {"username": name, "password": "pw-Str0ng-pass"})

    def assign(self, name, role, subjects=()):
        a = StaffAssignment.objects.create(user=make_user(name), role=role)
        a.subjects.set(subjects)

    def test_single_page_role_lands_on_that_page(self):
        self.assign("alice", self.reviewer, [self.phys])
        self.assertEqual(self.login("alice")["Location"], "/panel/formulas/")

    def test_multi_page_role_lands_on_dashboard(self):
        role = StaffRole.objects.create(name="Lead", access=["formulas.review", "users.students"])
        self.assign("bob", role, [self.phys])
        self.assertEqual(self.login("bob")["Location"], "/panel/")

    def test_student_goes_to_explore(self):
        u = make_user("sam")
        Profile.objects.create(user=u, grade="class-9", trial_ends_at=timezone.now())
        self.assertEqual(self.login("sam")["Location"], "/explore/")
        self.assertEqual(self.client.get("/panel/").status_code, 403)

    def test_pages_outside_the_role_are_blocked(self):
        self.assign("alice", self.reviewer, [self.phys])
        self.login("alice")
        for url in ("/panel/roles/", "/panel/staff/", "/panel/students/", "/panel/c/subjects/", "/panel/formulas/new/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_reviewer_only_sees_assigned_subject(self):
        self.assign("alice", self.reviewer, [self.phys])
        self.login("alice")
        r = self.client.get("/panel/formulas/")
        self.assertContains(r, "Ohm")
        self.assertNotContains(r, "Mole")
        self.assertEqual(self.client.get(f"/panel/formulas/{self.f_chem.pk}/").status_code, 404)

    def test_editing_a_role_changes_access_for_existing_users(self):
        self.assign("alice", self.reviewer, [self.phys])
        self.login("alice")
        self.assertEqual(self.client.get("/panel/students/").status_code, 403)
        self.reviewer.access = ["formulas.review", "users.students"]
        self.reviewer.save()
        self.assertEqual(self.client.get("/panel/students/").status_code, 200)

    def test_role_manager_cannot_hand_out_access_they_lack(self):
        mgr = StaffRole.objects.create(name="Manager", access=["admin.roles", "admin.staff"])
        self.assign("mia", mgr)
        self.login("mia")
        self.client.post("/panel/roles/new/", {"name": "Sneaky", "description": "",
                                               "access": ["admin.roles", "formulas.publish"]})
        self.assertEqual(StaffRole.objects.get(name="Sneaky").access,
                         ["roles.add", "roles.change", "roles.delete", "roles.view"])

    def test_admin_creates_role_and_user_in_the_panel(self):
        admin = make_user("root", is_superuser=True)
        self.client.force_login(admin)
        self.client.post("/panel/roles/new/", {"name": "Checker", "description": "", "access": ["formulas.review"]})
        role = StaffRole.objects.get(name="Checker")
        self.client.post("/panel/staff/new/", {"username": "newbie", "email": "n@example.com", "password": "pw-Str0ng-pass",
                                               "role": role.pk, "subjects": [self.phys.pk], "qualification": "PhD", "is_active": "on"})
        self.assertTrue(StaffAssignment.objects.filter(user__username="newbie", role=role).exists())
        self.client.logout()
        self.assertEqual(self.login("newbie")["Location"], "/panel/formulas/")

    def test_subject_role_needs_subjects(self):
        admin = make_user("root", is_superuser=True)
        self.client.force_login(admin)
        r = self.client.post("/panel/staff/new/", {"username": "x1", "email": "x@example.com", "password": "pw-Str0ng-pass",
                                                   "role": self.reviewer.pk, "qualification": ""})
        self.assertContains(r, "Choose at least one subject")


class PanelFeatureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.phys = Subject.objects.create(name="Physics", slug="physics")
        self.root = make_user("root", is_superuser=True)

    def login(self, name, pw="pw-Str0ng-pass"):
        return self.client.post("/login/", {"username": name, "password": pw})

    def assign(self, name, role, subjects=(), **kw):
        a = StaffAssignment.objects.create(user=make_user(name), role=role, **kw)
        a.subjects.set(subjects)
        return a

    def test_every_panel_page_is_guarded_by_its_own_code(self):
        """Adding a page to PAGES automatically adds it to this test."""
        for page in PAGES:
            name, kw = page["url"]
            url = reverse(name, kwargs=kw)
            yes = StaffRole.objects.create(name=f"yes-{page['key']}", access=[page["any"][0]])
            other = next(c[0] for c in ACCESS if c[0] not in page["any"])
            no = StaffRole.objects.create(name=f"no-{page['key']}", access=[other])
            self.assign(f"yes-{page['key']}", yes, [self.phys])
            self.assign(f"no-{page['key']}", no, [self.phys])
            self.client.force_login(User.objects.get(username=f"yes-{page['key']}"))
            self.assertEqual(self.client.get(url).status_code, 200, url)
            self.client.force_login(User.objects.get(username=f"no-{page['key']}"))
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_pausing_an_assignment_removes_access_and_resuming_restores_it(self):
        role = StaffRole.objects.create(name="Rev", access=["formulas.review"])
        a = self.assign("alice", role, [self.phys])
        self.client.force_login(self.root)
        self.client.post(reverse("panel:staff_toggle", args=[a.pk]))
        a.refresh_from_db()
        self.assertFalse(a.is_active)
        self.client.logout()
        self.assertEqual(self.login("alice")["Location"], "/explore/")
        self.assertEqual(self.client.get("/panel/formulas/").status_code, 403)
        self.client.force_login(self.root)
        self.client.post(reverse("panel:staff_toggle", args=[a.pk]))
        self.client.logout()
        self.assertEqual(self.login("alice")["Location"], "/panel/formulas/")

    def test_staff_manager_cannot_pause_themselves(self):
        role = StaffRole.objects.create(name="Mgr", access=["admin.staff"])
        a = self.assign("mia", role)
        self.client.force_login(a.user)
        self.client.post(reverse("panel:staff_toggle", args=[a.pk]))
        a.refresh_from_db()
        self.assertTrue(a.is_active)

    def test_role_default_subjects_fill_in_when_none_chosen(self):
        role = StaffRole.objects.create(name="Phys rev", access=["formulas.review"])
        role.default_subjects.set([self.phys])
        self.client.force_login(self.root)
        self.client.post("/panel/staff/new/", {"username": "dan", "email": "d@example.com", "password": "pw-Str0ng-pass",
                                               "role": role.pk, "qualification": "", "is_active": "on"})
        a = StaffAssignment.objects.get(user__username="dan")
        self.assertEqual(list(a.subjects.all()), [self.phys])

    def test_role_and_staff_changes_are_logged(self):
        self.client.force_login(self.root)
        self.client.post("/panel/roles/new/", {"name": "Checker", "description": "", "access": ["formulas.review"]})
        self.assertTrue(AuditLog.objects.filter(action="role.create", target="Checker", actor=self.root).exists())
        self.assertContains(self.client.get("/panel/audit/"), "role.create")

    def test_login_is_locked_after_repeated_failures(self):
        make_user("zed")
        for _ in range(5):
            self.login("zed", "wrong")
        self.assertEqual(self.login("zed").status_code, 429)
        self.assertTrue(AuditLog.objects.filter(action="login.locked", target="zed").exists())

    def test_two_factor_is_enforced_for_roles_that_require_it(self):
        role = StaffRole.objects.create(name="Pub", access=["formulas.review"], require_2fa=True)
        self.assign("pat", role, [self.phys])
        self.login("pat")
        self.assertEqual(self.client.get("/panel/formulas/")["Location"], "/panel/security/")
        self.client.post("/panel/security/", {"action": "start"})
        dev = TOTPDevice.objects.get(user__username="pat")
        self.client.post("/panel/security/", {"action": "setup", "code": "000000"})        # wrong code
        self.assertEqual(self.client.get("/panel/formulas/").status_code, 302)
        self.client.post("/panel/security/", {"action": "setup", "code": totp.code_at(dev.secret)})
        self.assertEqual(self.client.get("/panel/formulas/").status_code, 200)
        # a new sign-in asks for the code again
        self.client.logout()
        self.login("pat")
        self.assertEqual(self.client.get("/panel/formulas/").status_code, 302)
        self.client.post("/panel/security/", {"action": "verify", "code": totp.code_at(dev.secret)})
        self.assertEqual(self.client.get("/panel/formulas/").status_code, 200)

    def test_only_superuser_can_set_two_factor_on_a_role_and_reset_it(self):
        mgr = StaffRole.objects.create(name="Mgr", access=["admin.roles", "admin.staff"])
        a = self.assign("mia", mgr)
        self.client.force_login(a.user)
        self.client.post("/panel/roles/new/", {"name": "X", "description": "", "access": [], "require_2fa": "on"})
        self.assertFalse(StaffRole.objects.get(name="X").require_2fa)
        TOTPDevice.objects.create(user=a.user, secret=totp.new_secret(), confirmed=True)
        self.client.logout()
        self.client.force_login(self.root)
        self.client.post(reverse("panel:staff_reset2fa", args=[a.pk]))
        self.assertFalse(TOTPDevice.objects.filter(user=a.user).exists())

    def test_upgrade_roles_converts_old_checkboxes(self):
        r = StaffRole.objects.create(name="Old", can_create=True, can_review=True)
        call_command("upgrade_roles")
        r.refresh_from_db()
        self.assertEqual(sorted(r.access), ["formulas.create", "formulas.review"])


class TotpTests(TestCase):
    def test_rfc6238_vectors(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(totp.code_at(secret, 59, digits=8), "94287082")
        self.assertEqual(totp.code_at(secret, 1111111109, digits=8), "07081804")


class AccountTypeSignupTests(TestCase):
    def setUp(self):
        from accounts.models import AccountType
        tax.load_levels(); tax.load_grades()
        self.student = AccountType.objects.create(name="Student", slug="student", asks_grade=True)
        self.teacher = AccountType.objects.create(name="Teacher", slug="teacher", default_grade="undergraduate")
        self.hidden = AccountType.objects.create(name="Old", slug="old", default_grade="research", is_active=False)

    def post(self, **kw):
        data = {"username": "newuser", "email": "n@example.com", "password": "pw-Str0ng-pass!9", "password2": "pw-Str0ng-pass!9"}
        data.update(kw)
        return self.client.post("/register/", data)

    def test_student_must_choose_grade(self):
        r = self.post(account_type=self.student.pk)
        self.assertContains(r, "Select your grade.")
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_student_with_grade_is_created(self):
        self.post(account_type=self.student.pk, grade="class-9")
        p = User.objects.get(username="newuser").profile
        self.assertEqual((p.account_type, p.grade), (self.student, "class-9"))

    def test_teacher_needs_no_grade_and_gets_the_types_level(self):
        self.post(account_type=self.teacher.pk, grade="class-1")     # a posted grade is ignored
        p = User.objects.get(username="newuser").profile
        self.assertEqual((p.account_type, p.grade), (self.teacher, "undergraduate"))

    def test_type_is_required_and_hidden_types_are_refused(self):
        self.assertContains(self.post(), "Select who you are")
        self.assertContains(self.post(account_type=self.hidden.pk), "Select who you are")
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_only_a_role_with_the_code_can_manage_types(self):
        role = StaffRole.objects.create(name="TypeAdmin", access=["admin.account_types"])
        u = make_user("ta")
        StaffAssignment.objects.create(user=u, role=role)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/panel/c/account_types/").status_code, 200)
        other = make_user("nobody")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/panel/c/account_types/").status_code, 403)


class PerActionAccessTests(TestCase):
    """Add, change, delete and view are separate ticks, like the school timetable app."""

    def setUp(self):
        cache.clear()
        self.subject = Subject.objects.create(name="Physics", slug="physics")

    def user_with(self, *codes):
        role = StaffRole.objects.create(name="r-" + "-".join(codes), access=list(codes))
        u = make_user("u" + str(StaffRole.objects.count()))
        StaffAssignment.objects.create(user=u, role=role)
        self.client.force_login(u)
        return u

    def test_view_only_can_list_but_not_add_edit_or_delete(self):
        self.user_with("subjects.view")
        self.assertEqual(self.client.get("/panel/c/subjects/").status_code, 200)
        self.assertNotContains(self.client.get("/panel/c/subjects/"), "Add subject")
        self.assertEqual(self.client.get("/panel/c/subjects/new/").status_code, 403)
        self.assertEqual(self.client.get(f"/panel/c/subjects/{self.subject.pk}/edit/").status_code, 403)
        self.assertEqual(self.client.post(f"/panel/c/subjects/{self.subject.pk}/delete/").status_code, 403)
        self.assertTrue(Subject.objects.filter(pk=self.subject.pk).exists())

    def test_add_without_delete(self):
        self.user_with("subjects.view", "subjects.add")
        self.assertEqual(self.client.get("/panel/c/subjects/new/").status_code, 200)
        self.assertEqual(self.client.post(f"/panel/c/subjects/{self.subject.pk}/delete/").status_code, 403)

    def test_delete_works_with_delete_tick(self):
        self.user_with("subjects.view", "subjects.delete")
        self.client.post(f"/panel/c/subjects/{self.subject.pk}/delete/")
        self.assertFalse(Subject.objects.filter(pk=self.subject.pk).exists())

    def test_role_form_shows_four_ticks_per_area(self):
        self.user_with("roles.view", "roles.add")
        r = self.client.get("/panel/roles/new/")
        for word in ("Can add subject", "Can change subject", "Can delete subject", "Can view subject"):
            self.assertContains(r, word)

    def test_old_broad_codes_still_work(self):
        self.user_with("content.taxonomy")
        self.assertEqual(self.client.get("/panel/c/subjects/new/").status_code, 200)


class GradeAccessTests(TestCase):
    """An account type can open its own grade, extra grades, or every grade."""

    def setUp(self):
        from accounts.access import in_grade, restrict_queryset
        from accounts.models import AccountType
        self.in_grade, self.restrict = in_grade, restrict_queryset
        self.AccountType = AccountType
        tax.load_levels(); tax.load_grades()
        school, ug, res = (AcademicLevel.objects.get(slug=s) for s in ("school", "undergraduate", "research"))
        self.f_school = Formula.objects.create(title="A", slug="a", latex="a", short_explanation="x", min_class=5)
        self.f_school.levels.add(school)
        self.f_ug = Formula.objects.create(title="B", slug="b", latex="b", short_explanation="x")
        self.f_ug.levels.add(ug)
        self.f_res = Formula.objects.create(title="C", slug="c", latex="c", short_explanation="x")
        self.f_res.levels.add(res)

    def person(self, name, atype, grade):
        u = make_user(name)
        p = Profile.objects.create(user=u, account_type=atype, grade=grade, trial_ends_at=timezone.now())
        return u, p

    def titles(self, user):
        return sorted(self.restrict(user, Formula.objects.all()).values_list("title", flat=True))

    def test_own_grade_only(self):
        t = self.AccountType.objects.create(name="Student", slug="student", asks_grade=True)
        u, p = self.person("s1", t, "class-9")
        self.assertEqual(self.titles(u), ["A"])
        self.assertTrue(self.in_grade(p, self.f_school))
        self.assertFalse(self.in_grade(p, self.f_res))

    def test_class_below_the_minimum_is_still_blocked(self):
        t = self.AccountType.objects.create(name="Student", slug="student", asks_grade=True)
        u, p = self.person("s2", t, "class-3")
        self.assertEqual(self.titles(u), [])

    def test_extra_grades_are_added(self):
        t = self.AccountType.objects.create(name="Teacher", slug="teacher", default_grade="undergraduate",
                                            allowed_grades=["class-12", "research"])
        u, p = self.person("t1", t, "undergraduate")
        self.assertEqual(self.titles(u), ["A", "B", "C"])

    def test_every_grade(self):
        t = self.AccountType.objects.create(name="Professor", slug="professor", default_grade="postgraduate", all_grades=True)
        u, p = self.person("p1", t, "postgraduate")
        self.assertEqual(self.titles(u), ["A", "B", "C"])
        self.assertTrue(all(self.in_grade(p, f) for f in (self.f_school, self.f_ug, self.f_res)))

    def test_form_saves_extra_grades_and_every_grade_clears_them(self):
        admin = make_user("root", is_superuser=True)
        self.client.force_login(admin)
        self.client.post("/panel/c/account_types/new/", {
            "name": "Teacher", "slug": "", "description": "", "default_grade": "undergraduate",
            "allowed_grades": ["class-10", "research"], "is_active": "on", "sort_order": 0})
        t = self.AccountType.objects.get(name="Teacher")
        self.assertEqual(sorted(t.allowed_grades), ["class-10", "research"])
        self.client.post(f"/panel/c/account_types/{t.pk}/edit/", {
            "name": "Teacher", "slug": t.slug, "description": "", "default_grade": "undergraduate",
            "all_grades": "on", "allowed_grades": ["research"], "is_active": "on", "sort_order": 0})
        t.refresh_from_db()
        self.assertTrue(t.all_grades)
        self.assertEqual(t.allowed_grades, [])


class SoftCodedGradeTests(TestCase):
    """Grades, roles' grade access and the data files are all data, not code."""

    def setUp(self):
        cache.clear()
        tax.load_levels(); tax.load_grades(); tax.load_subjects()
        school, ug = AcademicLevel.objects.get(slug="school"), AcademicLevel.objects.get(slug="undergraduate")
        self.f_school = Formula.objects.create(title="A", slug="a", latex="a", short_explanation="x", min_class=5,
                                               status="published", access_tier="premium")
        self.f_school.levels.add(school)
        self.f_ug = Formula.objects.create(title="B", slug="b", latex="b", short_explanation="x", status="published")
        self.f_ug.levels.add(ug)

    def admin(self):
        u = make_user("root", is_superuser=True)
        self.client.force_login(u)
        return u

    # --- the grade list lives in the table
    def test_signup_offers_grades_from_the_table_and_a_new_grade_works_at_once(self):
        from accounts.models import AccountType
        AccountType.objects.create(name="Student", slug="student", asks_grade=True)
        Grade.objects.create(name="Diploma", slug="diploma", level=AcademicLevel.objects.get(slug="undergraduate"), sort_order=99)
        r = self.client.get("/register/")
        self.assertContains(r, "Diploma"); self.assertContains(r, "Class 9")
        t = AccountType.objects.get(slug="student")
        self.client.post("/register/", {"username": "dee", "email": "d@example.com", "password": "pw-Str0ng-pass!9",
                                        "password2": "pw-Str0ng-pass!9", "account_type": t.pk, "grade": "diploma"})
        self.assertEqual(User.objects.get(username="dee").profile.grade, "diploma")

    def test_hidden_grade_is_not_offered_or_accepted_on_signup(self):
        from accounts.models import AccountType
        t = AccountType.objects.create(name="Student", slug="student", asks_grade=True)
        Grade.objects.filter(slug="class-9").update(is_active=False)
        self.assertNotContains(self.client.get("/register/"), "Class 9")
        r = self.client.post("/register/", {"username": "x", "email": "x@example.com", "password": "pw-Str0ng-pass!9",
                                            "password2": "pw-Str0ng-pass!9", "account_type": t.pk, "grade": "class-9"})
        self.assertContains(r, "Select your grade.")

    def test_grade_in_use_cannot_be_deleted_and_its_code_is_locked(self):
        self.admin()
        u = make_user("kid")
        Profile.objects.create(user=u, grade="class-9", trial_ends_at=timezone.now())
        g = Grade.objects.get(slug="class-9")
        r = self.client.post(f"/panel/c/grades/{g.pk}/delete/", follow=True)
        self.assertTrue(Grade.objects.filter(pk=g.pk).exists())
        self.assertContains(r, "still used by 1 people")
        self.client.post(f"/panel/c/grades/{g.pk}/edit/", {"name": "Class Nine", "slug": "changed", "level": g.level_id,
                                                          "number": 9, "default_tier": "basic", "default_difficulty": "beginner",
                                                          "sort_order": 9, "is_active": "on"})
        g.refresh_from_db()
        self.assertEqual((g.name, g.slug), ("Class Nine", "class-9"))

    def test_unused_grade_can_be_added_and_deleted_in_the_panel(self):
        self.admin()
        lvl = AcademicLevel.objects.get(slug="undergraduate")
        self.client.post("/panel/c/grades/new/", {"name": "Diploma Year 1", "slug": "", "level": lvl.pk, "number": "",
                                                  "default_tier": "premium", "default_difficulty": "advanced",
                                                  "sort_order": 50, "is_active": "on"})
        g = Grade.objects.get(name="Diploma Year 1")
        self.assertEqual(g.slug, "diploma-year-1")
        self.client.post(f"/panel/c/grades/{g.pk}/delete/")
        self.assertFalse(Grade.objects.filter(pk=g.pk).exists())

    def test_students_page_shows_grade_names(self):
        self.admin()
        Profile.objects.create(user=make_user("kid"), grade="class-9", trial_ends_at=timezone.now())
        self.assertContains(self.client.get("/panel/students/"), "Class 9")

    def test_api_grades_endpoint(self):
        rows = self.client.get("/api/v1/grades/").json()
        self.assertIn("class-9", [r["slug"] for r in rows])
        self.assertEqual(rows[0]["slug"], "class-1")

    # --- roles can be given grade access
    def staff(self, name, **role_kw):
        role = StaffRole.objects.create(name="R-" + name, access=["formulas.review"], **role_kw)
        u = make_user(name)
        StaffAssignment.objects.create(user=u, role=role)
        return u

    def titles(self, user):
        from accounts.access import restrict_queryset
        return sorted(restrict_queryset(user, Formula.objects.all()).values_list("title", flat=True))

    def test_role_with_a_grade_can_open_that_grade_without_a_plan(self):
        from accounts.access import can_view
        u = self.staff("rita", grades=["undergraduate"])
        self.assertTrue(can_view(u, self.f_ug))
        self.assertFalse(can_view(u, self.f_school))
        self.assertEqual(self.titles(u), ["B"])
        self.client.force_login(u)
        self.assertEqual(self.client.get("/formulas/b/").status_code, 200)
        self.assertEqual(self.client.get("/formulas/a/").status_code, 302)      # sent to the pricing page

    def test_role_with_every_grade(self):
        u = self.staff("evan", all_grades=True)
        self.assertEqual(self.titles(u), ["A", "B"])

    def test_paused_assignment_gives_no_grades(self):
        from accounts.access import can_view
        u = self.staff("pat", grades=["undergraduate"])
        StaffAssignment.objects.filter(user=u).update(is_active=False)
        self.assertFalse(can_view(u, self.f_ug))

    def test_role_grades_add_to_the_profile_grade(self):
        from accounts.access import can_view
        u = self.staff("both", grades=["undergraduate"])
        Profile.objects.create(user=u, grade="class-9", premium_until=timezone.now() + timezone.timedelta(days=5),
                               trial_ends_at=timezone.now())
        self.assertTrue(can_view(u, self.f_ug))
        self.assertTrue(can_view(u, self.f_school))

    def test_role_form_saves_grades_and_logs_them(self):
        self.admin()
        self.client.post("/panel/roles/new/", {"name": "Viewer", "description": "", "access": ["formulas.review"],
                                               "grades": ["class-9", "undergraduate"]})
        r = StaffRole.objects.get(name="Viewer")
        self.assertEqual(sorted(r.grades), ["class-9", "undergraduate"])
        self.assertFalse(r.all_grades)
        self.assertTrue(AuditLog.objects.filter(action="role.create", detail__contains="grades added").exists())
        self.assertContains(self.client.get("/panel/roles/"), "Class 9, Undergraduate")

    def test_role_editor_cannot_hand_out_grades_they_do_not_hold(self):
        mgr = StaffRole.objects.create(name="Mgr", access=["roles.view", "roles.add", "roles.change"], grades=["class-9"])
        u = make_user("mgr"); StaffAssignment.objects.create(user=u, role=mgr)
        self.client.force_login(u)
        self.client.post("/panel/roles/new/", {"name": "Sneaky", "description": "", "access": ["roles.view"],
                                               "grades": ["research"], "all_grades": "on"})
        self.assertFalse(StaffRole.objects.filter(name="Sneaky").exists())       # research is not on offer to them
        self.client.post("/panel/roles/new/", {"name": "Ok", "description": "", "access": ["roles.view"],
                                               "grades": ["class-9"], "all_grades": "on"})
        ok = StaffRole.objects.get(name="Ok")
        self.assertEqual(ok.grades, ["class-9"])
        self.assertFalse(ok.all_grades)                                          # "every grade" needs holding it

    def test_editing_keeps_grades_the_editor_cannot_see(self):
        mgr = StaffRole.objects.create(name="Mgr", access=["roles.view", "roles.add", "roles.change"], grades=["class-9"])
        u = make_user("mgr"); StaffAssignment.objects.create(user=u, role=mgr)
        target = StaffRole.objects.create(name="T", access=["roles.view"], grades=["research", "class-9"])
        self.client.force_login(u)
        self.client.post(f"/panel/roles/{target.pk}/edit/", {"name": "T", "description": "", "access": ["roles.view"], "grades": []})
        target.refresh_from_db()
        self.assertEqual(target.grades, ["research"])

    # --- numbers come from settings
    def test_premium_grant_days_and_trial_days_come_from_settings(self):
        from datetime import timedelta
        from django.test import override_settings
        self.admin()
        p = Profile.objects.create(user=make_user("kid"), grade="class-9", trial_ends_at=timezone.now())
        with override_settings(PREMIUM_GRANT_DAYS=10):
            self.client.post(f"/panel/students/{p.pk}/grant/")
            self.assertContains(self.client.get("/panel/students/"), "Grant 10 days")
        p.refresh_from_db()
        self.assertAlmostEqual((p.premium_until - timezone.now()).days, 10, delta=1)

    # --- the data files
    def test_data_files_have_no_mistakes(self):
        from formulas import seeding
        self.assertEqual(seeding.check(), [])

    def test_seed_content_loads_everything_and_is_safe_to_repeat(self):
        from io import StringIO
        out = StringIO()
        call_command("seed_content", stdout=out)
        n = Formula.objects.count()
        self.assertGreater(n, 600)
        self.assertEqual(Subject.objects.filter(is_published=True).count(), 10)
        self.assertEqual(Formula.objects.filter(is_demo=True, topics__isnull=True).count(), 0)
        call_command("seed_content", stdout=StringIO())
        self.assertEqual(Formula.objects.count(), n)

    def test_seed_uses_the_grades_defaults_and_levels(self):
        call_command("seed_content", stdout=__import__("io").StringIO())
        f = Formula.objects.get(title="Area of a circle")           # class 7
        self.assertEqual((f.min_class, f.access_tier, f.difficulty), (7, "basic", "beginner"))
        self.assertEqual(list(f.levels.values_list("slug", flat=True)), ["school"])
        r = Formula.objects.get(title="Hawking temperature")
        self.assertEqual((r.access_tier, list(r.levels.values_list("slug", flat=True))), ("premium", ["research"]))

    def test_a_new_data_folder_adds_a_grade_subject_and_formula_without_code(self):
        import tempfile, shutil
        from pathlib import Path
        from io import StringIO
        src = tax.DEFAULT_DIR
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("levels.txt", "grades.txt", "subjects.txt"):
                shutil.copy(src / name, d / name)
            (d / "formulas").mkdir()
            with open(d / "grades.txt", "a") as f:
                f.write("D1|diploma-1|Diploma Year 1|undergraduate||premium|intermediate|20\n")
            with open(d / "subjects.txt", "a") as f:
                f.write("G|Geography|Maps and measurement.\n")
            (d / "formulas" / "geo.txt").write_text("G|D1|Scale of a map|\\text{scale}=\\frac{\\text{map distance}}{\\text{ground distance}}|Ratio of map to ground.\n")
            call_command("seed_content", dir=str(d), stdout=StringIO())
        f = Formula.objects.get(title="Scale of a map")
        self.assertEqual((f.difficulty, f.min_class), ("intermediate", None))
        self.assertTrue(Subject.objects.filter(name="Geography").exists())
        self.assertTrue(Grade.objects.filter(slug="diploma-1").exists())

    def test_check_reports_bad_lines(self):
        import tempfile, shutil
        from pathlib import Path
        from formulas import seeding
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("levels.txt", "grades.txt", "subjects.txt"):
                shutil.copy(tax.DEFAULT_DIR / name, d / name)
            (d / "formulas").mkdir()
            (d / "formulas" / "bad.txt").write_text("X|S9|One|a|b\nM|S99|Two|a|b\nM|S9|One|a|b\n")
            problems = " ".join(seeding.check(d))
        for word in ("unknown subject code 'X'", "unknown grade code 'S99'", "title 'One' is already used"):
            self.assertIn(word, problems)

    def test_account_type_and_role_seed_files(self):
        from io import StringIO
        from accounts.models import AccountType
        call_command("seed_account_types", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(AccountType.objects.get(slug="professor").all_grades, True)
        self.assertEqual(AccountType.objects.get(slug="teacher").default_grade, "undergraduate")
        cm = StaffRole.objects.get(name="Content manager")
        self.assertIn("grades.change", cm.access)
        self.assertTrue(cm.all_grades)
        self.assertFalse(StaffRole.objects.get(name="Student support").all_grades)
