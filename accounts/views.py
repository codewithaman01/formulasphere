from datetime import timedelta
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .access import get_profile
from . import lockout
from .scope import landing_url
from taxonomy.models import Grade
from . import emails, payments
from .models import AccountType, PlanRequest, PremiumPlan, Profile

User = get_user_model()


def register(request):
    types = list(AccountType.objects.filter(is_active=True))
    grades = list(Grade.objects.filter(is_active=True).select_related("level").order_by("level__sort_order", "sort_order", "name"))
    ctx = {"grades": grades, "types": types, "errors": [], "values": request.POST, "trial_days": settings.TRIAL_DAYS}
    if request.method == "POST":
        p = request.POST
        username, email, pw = p.get("username", "").strip(), p.get("email", "").strip(), p.get("password", "")
        errors = []
        atype = next((t for t in types if str(t.pk) == p.get("account_type", "")), None)
        grade = ""
        if atype is None:
            errors.append("Select who you are (for example Student or Teacher).")
        elif atype.asks_grade:
            grade = p.get("grade", "")
            if grade not in {g.slug for g in grades}:
                errors.append("Select your grade.")
        else:
            grade = atype.default_grade      # grade list is not shown for this type; the admin set its level
        if not username:
            errors.append("Enter a username.")
        elif User.objects.filter(username__iexact=username).exists():
            errors.append("That username is taken.")
        if "@" not in email:
            errors.append("Enter a valid email address.")
        if pw != p.get("password2", ""):
            errors.append("The two passwords do not match.")
        else:
            try:
                validate_password(pw, User(username=username, email=email))
            except ValidationError as e:
                errors += e.messages
        if not errors:
            user = User.objects.create_user(username=username, email=email, password=pw)
            profile = Profile.objects.create(user=user, account_type=atype, grade=grade,
                                             trial_ends_at=timezone.now() + timedelta(days=settings.TRIAL_DAYS))
            login(request, user)
            emails.send_welcome(user, profile)
            return redirect("explore")
        ctx["errors"] = errors
    return render(request, "web/register.html", ctx)


def login_view(request):
    error = ""
    nxt = request.POST.get("next") or request.GET.get("next", "")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        if lockout.login_blocked(request, username):
            error = "Too many failed attempts. Please wait 15 minutes and try again."
            return render(request, "web/login.html", {"error": error, "next": nxt}, status=429)
        user = authenticate(request, username=username, password=request.POST.get("password", ""))
        if user:
            lockout.login_ok(request, username)
            login(request, user)
            ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})
            if ok and nxt:
                return redirect(nxt)
            return redirect(landing_url(user))     # panel page(s) for staff, Explore for students
        lockout.login_failed(request, username)
        error = "Username or password is incorrect."
    return render(request, "web/login.html", {"error": error, "next": nxt})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


def pricing(request):
    mine = PlanRequest.objects.filter(user=request.user).select_related("plan")[:5] if request.user.is_authenticated else []
    return render(request, "web/pricing.html", {
        "profile": get_profile(request.user), "trial_days": settings.TRIAL_DAYS,
        "plans": PremiumPlan.objects.filter(is_active=True), "requests": mine, "online_pay": payments.enabled(),
        "instructions": settings.PAYMENT_INSTRUCTIONS})


@login_required
@require_POST
def plan_choose(request, slug):
    plan = get_object_or_404(PremiumPlan, slug=slug, is_active=True)
    req = PlanRequest.objects.filter(user=request.user, plan=plan, status="pending").first()
    if req is None:
        PlanRequest.objects.create(user=request.user, plan=plan, amount=plan.price)
    messages.success(request, f"You chose {plan.name}. Pay {settings.CURRENCY_SYMBOL}{plan.price:g} and enter the payment reference below. "
                              "Premium starts as soon as we confirm the payment.")
    return redirect("pricing")


@login_required
@require_POST
def plan_reference(request, pk):
    req = get_object_or_404(PlanRequest, pk=pk, user=request.user, status="pending")
    req.reference = request.POST.get("reference", "").strip()[:120]
    req.save(update_fields=["reference"])
    messages.success(request, "Thank you. We will check the payment and activate Premium.")
    return redirect("pricing")


@login_required
@require_POST
def plan_cancel(request, pk):
    PlanRequest.objects.filter(pk=pk, user=request.user, status="pending").update(status="cancelled")
    return redirect("pricing")


# ------------------------------------------------------------ online payment (Razorpay)
@login_required
@require_POST
def pay_start(request, pk):
    """Creates (or reuses) the Razorpay order for one pending plan request and returns what Checkout needs."""
    if not payments.enabled():
        return JsonResponse({"error": "Online payment is not switched on."}, status=400)
    req = get_object_or_404(PlanRequest.objects.select_related("plan"), pk=pk, user=request.user, status="pending")
    try:
        if not req.gateway_order_id:
            req.gateway_order_id = payments.create_order(req)
            req.save(update_fields=["gateway_order_id"])
    except payments.PaymentError as e:
        return JsonResponse({"error": str(e)}, status=502)
    return JsonResponse({"key": settings.RAZORPAY_KEY_ID, "order_id": req.gateway_order_id,
                         "amount": payments.amount_in_paise(req.amount), "currency": settings.PAYMENT_CURRENCY,
                         "name": "FormulaSphere", "description": req.plan.name,
                         "prefill": {"email": request.user.email}})


@login_required
@require_POST
def pay_verify(request, pk):
    """Called by the browser after Checkout. The signature proves Razorpay (not the visitor) made the payment."""
    req = get_object_or_404(PlanRequest, pk=pk, user=request.user)
    order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    ok = (order_id == req.gateway_order_id and
          payments.verify_checkout_signature(order_id, payment_id, request.POST.get("razorpay_signature", "")))
    if not ok:
        return JsonResponse({"error": "We could not confirm this payment. If money was taken, contact us with the payment id."}, status=400)
    payments.mark_paid(order_id, payment_id)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Razorpay calls this by itself, so a closed browser tab can never lose a payment."""
    if not payments.verify_webhook_signature(request.body, request.headers.get("X-Razorpay-Signature", "")):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body.decode())
        if event.get("event") in ("payment.captured", "order.paid"):
            pay = event["payload"]["payment"]["entity"]
            payments.mark_paid(pay.get("order_id", ""), pay.get("id", ""), pay.get("amount"))
    except (ValueError, KeyError, TypeError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)
