from bson import ObjectId
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from config.prefetch import prefetch
from taxonomy.models import Grade, Subject
from .models import ClassRegistration, Course, Enrollment, LiveClass, TuitionEnquiry, TuitionOffer


def _grades():
    return Grade.objects.filter(is_active=True).select_related("level").order_by("level__sort_order", "sort_order", "name")


def _filters(request, qs):
    """subject and grade filters shared by the three lists."""
    subject, grade = request.GET.get("subject", ""), request.GET.get("grade", "")
    if subject:
        qs = qs.filter(subject__slug=subject)
    if grade:
        qs = qs.filter(grades__slug=grade)
    return qs.distinct(), {"subject": subject, "grade": grade}


def _ctx(request, extra):
    base = {"subjects": Subject.objects.filter(is_published=True), "grades": _grades(), "filters": {}}
    base.update(extra)
    return base


def is_registered(user, lc):
    """Registered directly, or enrolled (active) in the class's course."""
    if not user.is_authenticated:
        return False
    if lc.registrations.filter(user=user).exists():
        return True
    return bool(lc.course_id and Enrollment.objects.filter(user=user, course_id=lc.course_id, status="active").exists())


def courses(request):
    qs = Course.objects.filter(is_published=True).select_related("subject")
    qs, f = _filters(request, qs)
    return render(request, "learning/courses.html", _ctx(request, {"courses": prefetch(list(qs), "grades"), "filters": f}))


def course_detail(request, slug):
    c = get_object_or_404(Course.objects.select_related("subject", "teacher"), slug=slug, is_published=True)
    prefetch([c], "grades", "topics__subject")
    enrol = Enrollment.objects.filter(user=request.user, course=c).first() if request.user.is_authenticated else None
    upcoming = c.live_classes.filter(is_published=True, starts_at__gte=timezone.now() - timezone.timedelta(hours=3))
    return render(request, "learning/course_detail.html", {"c": c, "enrol": enrol, "upcoming": upcoming})


@login_required
@require_POST
def enroll(request, slug):
    c = get_object_or_404(Course, slug=slug, is_published=True)
    e, new = Enrollment.objects.get_or_create(user=request.user, course=c,
                                               defaults={"status": "active" if c.is_free else "pending"})
    if not new and e.status == "cancelled":
        e.status = "active" if c.is_free else "pending"
        e.save()
    if e.status == "active":
        messages.success(request, f"You are enrolled in {c.title}.")
    else:
        messages.success(request, "Thank you. Your place is saved and will open as soon as the payment is confirmed.")
    return redirect("learning:course", slug=slug)


def live_list(request):
    now = timezone.now()
    qs = LiveClass.objects.filter(is_published=True).select_related("subject", "course")
    qs, f = _filters(request, qs)
    items = prefetch(list(qs), "grades")
    upcoming = [l for l in items if l.ends_at >= now]
    recent = [l for l in reversed(items) if l.starts_at < now and l.ends_at < now][:6]
    mine = set(ClassRegistration.objects.filter(user=request.user).values_list("live_class_id", flat=True)) if request.user.is_authenticated else set()
    return render(request, "learning/live_list.html", _ctx(request, {"upcoming": upcoming, "recent": recent, "mine": mine, "filters": f}))


def live_detail(request, slug):
    lc = get_object_or_404(LiveClass.objects.select_related("subject", "course", "teacher"), slug=slug, is_published=True)
    prefetch([lc], "grades")
    reg = is_registered(request.user, lc)
    return render(request, "learning/live_detail.html", {
        "lc": lc, "registered": reg, "show_join": reg and lc.join_url and lc.join_open(),
        "show_recording": reg and lc.recording_url and lc.is_over,
        "early": settings.LIVE_JOIN_EARLY_MINUTES})


@login_required
@require_POST
def live_register(request, slug):
    lc = get_object_or_404(LiveClass, slug=slug, is_published=True)
    if lc.is_over:
        messages.error(request, "This class has already finished.")
    elif is_registered(request.user, lc):
        messages.success(request, "You are already registered.")
    elif lc.is_full:
        messages.error(request, "Sorry, this class is full.")
    else:
        ClassRegistration.objects.get_or_create(user=request.user, live_class=lc)
        messages.success(request, "You are registered. The meeting link will appear on this page shortly before the class.")
    return redirect("learning:live_detail", slug=slug)


@login_required
@require_POST
def live_unregister(request, slug):
    lc = get_object_or_404(LiveClass, slug=slug)
    ClassRegistration.objects.filter(user=request.user, live_class=lc).delete()
    messages.success(request, "Your registration was cancelled.")
    return redirect("learning:live_detail", slug=slug)


def tuition(request):
    qs = TuitionOffer.objects.filter(is_published=True).select_related("subject")
    qs, f = _filters(request, qs)
    qs = prefetch(list(qs), "grades")
    errors, values = [], request.POST if request.method == "POST" else {}
    if request.method == "POST":
        ip = request.META.get("REMOTE_ADDR", "?")
        key, limit = f"enquiry:{ip}", getattr(settings, "ENQUIRY_LIMIT", 5)
        name, phone, email = (request.POST.get(k, "").strip() for k in ("name", "phone", "email"))
        grade = request.POST.get("grade", "")
        if request.POST.get("website"):                       # hidden field that only bots fill in
            return redirect("learning:tuition")
        if not name:
            errors.append("Please enter your name.")
        if not phone and not email:
            errors.append("Please give a phone number or an email so we can reach you.")
        if grade and not Grade.objects.filter(slug=grade).exists():
            errors.append("Please choose a grade from the list.")
        if cache.get(key, 0) >= limit:
            errors.append("Too many requests from your connection. Please try again later.")
        offer_id = request.POST.get("offer") or ""
        offer = (TuitionOffer.objects.filter(pk=ObjectId(offer_id), is_published=True).first()
                 if ObjectId.is_valid(offer_id) else None)
        if not errors:
            TuitionEnquiry.objects.create(
                offer=offer, user=request.user if request.user.is_authenticated else None, name=name, phone=phone, email=email,
                grade=grade, subject_wanted=request.POST.get("subject_wanted", "").strip()[:120],
                message=request.POST.get("message", "").strip()[:2000])
            cache.set(key, cache.get(key, 0) + 1, 3600)
            messages.success(request, "Thank you. We have your request and will contact you soon.")
            return redirect("learning:tuition")
    return render(request, "learning/tuition.html", _ctx(request, {"offers": qs, "filters": f, "errors": errors, "values": values}))


@login_required
def my_learning(request):
    now = timezone.now()
    regs = ClassRegistration.objects.filter(user=request.user, live_class__is_published=True).select_related("live_class")
    return render(request, "learning/my.html", {
        "enrollments": Enrollment.objects.filter(user=request.user).exclude(status="cancelled").select_related("course"),
        "upcoming": [r.live_class for r in regs if r.live_class.ends_at >= now],
        "enquiries": TuitionEnquiry.objects.filter(user=request.user).select_related("offer")})
