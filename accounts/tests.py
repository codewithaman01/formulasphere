"""python manage.py test accounts   (needs the MongoDB settings in .env)"""
import hashlib
import hmac
import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import AccountType, PlanRequest, PremiumPlan, Profile

User = get_user_model()


def make_student(name="stu", premium=False, trial_days=7):
    u = User.objects.create_user(name, f"{name}@example.com", "pw-Str0ng-pass")
    at, _ = AccountType.objects.get_or_create(slug="student", defaults=dict(name="Student", all_grades=True))
    now = timezone.now()
    Profile.objects.create(user=u, account_type=at, grade="class-9", trial_ends_at=now + timedelta(days=trial_days),
                           premium_until=now + timedelta(days=30) if premium else None)
    return u


class DeviceLimitTests(TestCase):
    @override_settings(MAX_SESSIONS=2)
    def test_oldest_device_is_signed_out(self):
        make_student("dev")
        clients = [Client() for _ in range(3)]
        for c in clients:
            self.assertTrue(c.login(username="dev", password="pw-Str0ng-pass"))
        self.assertNotEqual(clients[0].get("/saved/").status_code, 200)   # first device was signed out
        self.assertEqual(clients[1].get("/saved/").status_code, 200)
        self.assertEqual(clients[2].get("/saved/").status_code, 200)

    @override_settings(MAX_SESSIONS=1)
    def test_staff_are_exempt(self):
        User.objects.create_superuser("boss", "b@example.com", "pw-Str0ng-pass")
        a, b = Client(), Client()
        a.login(username="boss", password="pw-Str0ng-pass")
        b.login(username="boss", password="pw-Str0ng-pass")
        self.assertEqual(a.get("/panel/").status_code, 200)


@override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret123", RAZORPAY_WEBHOOK_SECRET="whsec")
class PaymentTests(TestCase):
    def setUp(self):
        self.user = make_student("payer")
        self.plan = PremiumPlan.objects.create(name="Monthly", slug="monthly", price=199, duration_days=30)
        self.req = PlanRequest.objects.create(user=self.user, plan=self.plan, amount=199, gateway_order_id="order_1")

    def sign(self, order, pay):
        return hmac.new(b"secret123", f"{order}|{pay}".encode(), hashlib.sha256).hexdigest()

    def test_checkout_signature_marks_paid_once(self):
        c = Client(); c.login(username="payer", password="pw-Str0ng-pass")
        data = {"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1", "razorpay_signature": self.sign("order_1", "pay_1")}
        self.assertEqual(c.post(f"/premium/requests/{self.req.pk}/verify/", data).status_code, 200)
        self.assertEqual(c.post(f"/premium/requests/{self.req.pk}/verify/", data).status_code, 200)   # repeated: no extra days
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "paid")
        days = (Profile.objects.get(user=self.user).premium_until - timezone.now()).days
        self.assertIn(days, (29, 30))
        self.assertEqual(len([m for m in mail.outbox if "Payment received" in m.subject]), 1)

    def test_bad_signature_is_refused(self):
        c = Client(); c.login(username="payer", password="pw-Str0ng-pass")
        r = c.post(f"/premium/requests/{self.req.pk}/verify/", {"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1", "razorpay_signature": "nope"})
        self.assertEqual(r.status_code, 400)
        self.req.refresh_from_db(); self.assertEqual(self.req.status, "pending")

    def _hook(self, body, sig=None):
        raw = json.dumps(body).encode()
        sig = sig or hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
        return Client().post("/hooks/razorpay/", raw, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig)

    def test_webhook_marks_paid(self):
        body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_1", "amount": 19900}}}}
        self.assertEqual(self._hook(body).status_code, 200)
        self.req.refresh_from_db(); self.assertEqual(self.req.status, "paid")

    def test_webhook_wrong_amount_or_signature_ignored(self):
        body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_1", "amount": 100}}}}
        self.assertEqual(self._hook(body).status_code, 200)
        self.req.refresh_from_db(); self.assertEqual(self.req.status, "pending")
        self.assertEqual(self._hook(body, sig="bad").status_code, 400)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_online_pay_off_without_keys(self):
        c = Client(); c.login(username="payer", password="pw-Str0ng-pass")
        self.assertEqual(c.post(f"/premium/requests/{self.req.pk}/pay/").status_code, 400)


class ReminderTests(TestCase):
    def test_reminders_sent_once(self):
        make_student("soon", trial_days=1)
        make_student("later", trial_days=6)
        make_student("prem", premium=True, trial_days=-3).profile    # premium ends in 30 days: no reminder yet
        out = StringIO()
        call_command("send_reminders", stdout=out)
        self.assertEqual([m.to for m in mail.outbox if "trial ends" in m.subject], [["soon@example.com"]])
        call_command("send_reminders", stdout=out)
        self.assertEqual(len([m for m in mail.outbox if "trial ends" in m.subject]), 1)
        p = Profile.objects.get(user__username="prem")
        p.premium_until = timezone.now() + timedelta(days=2); p.save()
        call_command("send_reminders", stdout=out); call_command("send_reminders", stdout=out)
        self.assertEqual(len([m for m in mail.outbox if "Premium ends" in m.subject]), 1)

    def test_welcome_email_on_signup(self):
        AccountType.objects.create(name="Student", slug="student", all_grades=True)
        r = Client().post("/register/", {"username": "newbie", "email": "n@example.com", "password": "Tr1cky-pass-77", "password2": "Tr1cky-pass-77",
                                         "account_type": AccountType.objects.get().pk})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(any("Welcome" in m.subject for m in mail.outbox))
