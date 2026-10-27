"""Razorpay (online payment). Nothing here runs until RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are set in .env.

Flow: the student presses Pay online -> create_order() -> Razorpay Checkout opens in the browser ->
Razorpay returns payment id + signature -> verify_checkout_signature() -> the plan request is marked paid
(Premium is added by PlanRequest.save, once). The webhook is a second route to the same mark_paid() so a
closed browser tab can never lose a payment.
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from decimal import Decimal
from django.conf import settings
from django.db import DatabaseError
from django_mongodb_backend import transaction


class PaymentError(Exception):
    pass


def enabled():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def amount_in_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_order(plan_request):
    body = json.dumps({"amount": amount_in_paise(plan_request.amount), "currency": settings.PAYMENT_CURRENCY,
                       "receipt": f"fs-{plan_request.pk}", "notes": {"plan_request": str(plan_request.pk)}}).encode()
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    req = urllib.request.Request("https://api.razorpay.com/v1/orders", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())["id"]
    except (urllib.error.URLError, KeyError, ValueError) as e:
        raise PaymentError("The payment service could not be reached. Please try again.") from e


def _hmac(secret, message):
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id, payment_id, signature):
    if not (order_id and payment_id and signature and settings.RAZORPAY_KEY_SECRET):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_KEY_SECRET, f"{order_id}|{payment_id}".encode()), signature)


def verify_webhook_signature(raw_body, signature):
    if not (signature and settings.RAZORPAY_WEBHOOK_SECRET):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_WEBHOOK_SECRET, raw_body), signature)


def mark_paid(order_id, payment_id, paid_paise=None):
    """Idempotent. Returns the PlanRequest, or None if the order is unknown or the amount does not match.

    The browser check and the webhook can arrive at the same moment. MongoDB has no row locks: instead, two
    transactions that change the same request collide and one of them fails. The loser simply tries again and
    then finds the request already paid, so Premium is added exactly once."""
    for attempt in range(4):
        try:
            return _mark_paid(order_id, payment_id, paid_paise)
        except DatabaseError:
            if attempt == 3:
                raise
    return None


@transaction.atomic
def _mark_paid(order_id, payment_id, paid_paise=None):
    from .models import PlanRequest
    req = PlanRequest.objects.filter(gateway_order_id=order_id).first()
    if req is None:
        return None
    if paid_paise is not None and int(paid_paise) != amount_in_paise(req.amount):
        return None
    if req.status != "paid":
        req.status = "paid"
        req.gateway_payment_id = payment_id[:60]
        req.reference = req.reference or payment_id[:120]
        req.staff_note = "Paid online (Razorpay)"
        req.save()              # PlanRequest.save adds the Premium days exactly once
    return req
