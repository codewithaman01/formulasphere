from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from taxonomy import seeding as tax
from .models import PlanRequest, PremiumPlan, Profile, StaffAssignment, StaffRole

User = get_user_model()


def user(name, **kw):
    return User.objects.create_user(name, f"{name}@example.com", "pw-Str0ng-pass!9", **kw)


class PremiumPlanTests(TestCase):
    def setUp(self):
        tax.load_levels(); tax.load_grades()
        self.monthly = PremiumPlan.objects.create(name="Monthly", slug="monthly", price=199, duration_days=30, is_active=True,
                                                  features="All formulas\nDerivations")
        self.yearly = PremiumPlan.objects.create(name="Yearly", slug="yearly", price=1200, original_price=2400, duration_days=365,
                                                 is_active=True, is_featured=True)
        self.hidden = PremiumPlan.objects.create(name="Secret", slug="secret", price=1, is_active=False)
        self.stu = user("stu")
        Profile.objects.create(user=self.stu, grade="class-9", trial_ends_at=timezone.now() - timedelta(days=1))

    def test_page_shows_amounts_features_and_only_active_plans(self):
        r = self.client.get("/premium/")
        self.assertContains(r, "Monthly"); self.assertContains(r, "199"); self.assertContains(r, "All formulas")
        self.assertContains(r, "Save 50%"); self.assertContains(r, "Most popular")
        self.assertNotContains(r, "Secret")

    def test_plan_maths(self):
        self.assertEqual((self.yearly.period_label, self.monthly.period_label), ("year", "month"))
        self.assertEqual(float(self.yearly.per_month), 98.63)
        self.assertEqual(self.yearly.saving_percent, 50); self.assertEqual(self.monthly.saving_percent, 0)
        self.assertEqual(self.monthly.feature_list, ["All formulas", "Derivations"])

    def test_choosing_a_plan_needs_sign_in_and_is_not_duplicated(self):
        self.assertEqual(self.client.post("/premium/monthly/choose/").status_code, 302)
        self.assertEqual(PlanRequest.objects.count(), 0)
        self.client.force_login(self.stu)
        self.client.post("/premium/monthly/choose/"); self.client.post("/premium/monthly/choose/")
        r = PlanRequest.objects.get()
        self.assertEqual((r.status, float(r.amount)), ("pending", 199.0))
        self.assertEqual(self.client.post("/premium/secret/choose/").status_code, 404)

    def test_student_adds_reference_and_can_cancel_only_their_own(self):
        self.client.force_login(self.stu); self.client.post("/premium/monthly/choose/")
        r = PlanRequest.objects.get()
        self.client.post(f"/premium/requests/{r.pk}/reference/", {"reference": "UPI123"})
        r.refresh_from_db(); self.assertEqual(r.reference, "UPI123")
        self.client.force_login(user("other"))
        self.client.post(f"/premium/requests/{r.pk}/cancel/")
        r.refresh_from_db(); self.assertEqual(r.status, "pending")
        self.client.force_login(self.stu); self.client.post(f"/premium/requests/{r.pk}/cancel/")
        r.refresh_from_db(); self.assertEqual(r.status, "cancelled")

    def test_paying_adds_the_days_once_and_extends_existing_premium(self):
        r = PlanRequest.objects.create(user=self.stu, plan=self.monthly)
        p = Profile.objects.get(user=self.stu)
        self.assertFalse(p.is_premium)
        r.status = "paid"; r.save(); r.save()                                  # saving twice must not add twice
        p.refresh_from_db()
        self.assertTrue(p.is_premium)
        self.assertAlmostEqual((p.premium_until - timezone.now()).days, 30, delta=1)
        PlanRequest.objects.create(user=self.stu, plan=self.yearly, status="paid")
        p.refresh_from_db()
        self.assertAlmostEqual((p.premium_until - timezone.now()).days, 395, delta=1)

    def test_staff_confirm_payment_in_the_panel(self):
        r = PlanRequest.objects.create(user=self.stu, plan=self.monthly)
        mgr = user("mgr")
        StaffAssignment.objects.create(user=mgr, role=StaffRole.objects.create(name="Cashier", access=["plan_requests.view", "plan_requests.change"]))
        self.client.force_login(mgr)
        self.assertContains(self.client.get("/panel/c/plan_requests/"), "stu")
        self.client.post(f"/panel/c/plan_requests/{r.pk}/edit/", {"user": self.stu.pk, "plan": self.monthly.pk, "amount": "199.00",
                                                                 "status": "paid", "reference": "UPI123", "staff_note": "Checked"})
        self.assertTrue(Profile.objects.get(user=self.stu).is_premium)
        self.assertEqual(self.client.get("/panel/c/plans/").status_code, 403)       # cashier cannot change prices

    def test_plans_are_managed_in_the_panel(self):
        self.client.force_login(user("root", is_superuser=True, is_staff=True))
        self.client.post("/panel/c/plans/new/", {"name": "Exam pack", "slug": "", "tagline": "", "price": "299", "original_price": "",
                                                 "duration_days": 60, "features": "A\nB", "description": "", "is_active": "on", "sort_order": 5})
        p = PremiumPlan.objects.get(name="Exam pack")
        self.assertEqual((p.slug, p.period_label, p.feature_list), ("exam-pack", "2 months", ["A", "B"]))
        self.assertContains(self.client.get("/premium/"), "Exam pack")

    def test_plan_that_has_requests_cannot_be_deleted(self):
        PlanRequest.objects.create(user=self.stu, plan=self.monthly)
        self.client.force_login(user("root", is_superuser=True, is_staff=True))
        self.client.post(f"/panel/c/plans/{self.monthly.pk}/delete/")
        self.assertTrue(PremiumPlan.objects.filter(pk=self.monthly.pk).exists())

    def test_seed_plans_creates_hidden_examples_once(self):
        PremiumPlan.objects.all().delete()
        call_command("seed_plans", stdout=StringIO()); call_command("seed_plans", stdout=StringIO())
        self.assertEqual(PremiumPlan.objects.count(), 3)
        self.assertFalse(PremiumPlan.objects.filter(is_active=True).exists())
        self.assertEqual(PremiumPlan.objects.get(slug="quarterly").is_featured, True)
        self.assertEqual(PremiumPlan.objects.get(slug="yearly").saving_percent, 37)


class ConcurrentPaymentTests(TransactionTestCase):
    """Webhook and browser check arriving together must add the Premium days exactly once."""

    def test_many_simultaneous_confirmations_add_days_once(self):
        import threading
        from django.db import connections
        from . import payments
        tax.load_levels(); tax.load_grades()
        plan = PremiumPlan.objects.create(name="Monthly", slug="monthly", price=199, duration_days=30, is_active=True)
        stu = user("racer")
        profile = Profile.objects.create(user=stu, grade="class-9", trial_ends_at=timezone.now() - timedelta(days=1))
        req = PlanRequest.objects.create(user=stu, plan=plan, amount=199, gateway_order_id="order_X")
        errors, results = [], []

        def worker():
            try:
                results.append(payments.mark_paid("order_X", "pay_1", 19900))
            except Exception as exc:                                    # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertTrue(all(r is not None for r in results))
        profile.refresh_from_db(); req.refresh_from_db()
        self.assertEqual(req.status, "paid")
        days = (profile.premium_until - timezone.now()).total_seconds() / 86400
        self.assertTrue(29.9 < days < 30.1, days)                      # 30 days, not 60 or 240
