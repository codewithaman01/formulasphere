from django.conf import settings
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from accounts import lockout
from accounts.access import can_view, get_profile, restrict_queryset
from formulas.search import published, search_formulas
from taxonomy.models import Grade, Subject
from .serializers import FormulaDetailSerializer, FormulaListSerializer, RegisterSerializer, SubjectSerializer


def profile_data(user):
    p = get_profile(user)
    if not p:
        return {"username": user.username, "plan": "staff" if (user.is_superuser or user.assignments.filter(is_active=True).exists()) else "none"}
    return {"username": user.username, "account_type": p.account_type.slug if p.account_type else settings.DEFAULT_ACCOUNT_TYPE,
            "account_type_label": p.account_type.name if p.account_type else settings.DEFAULT_ACCOUNT_TYPE.replace("-", " ").title(), "grade": p.grade, "grade_label": p.grade_name, "plan": p.plan,
            "trial_ends_at": p.trial_ends_at, "premium_until": p.premium_until}


@api_view(["GET"])
@permission_classes([AllowAny])
def account_types(request):
    """What the sign-up screen should offer. Grade list is needed only when asks_grade is true."""
    from accounts.models import AccountType
    return Response([{"slug": t.slug, "name": t.name, "description": t.description, "asks_grade": t.asks_grade}
                     for t in AccountType.objects.filter(is_active=True)])


@api_view(["GET"])
@permission_classes([AllowAny])
def grades(request):
    """The grade list for the sign-up screen. It comes from the Grades table, so the app never hard-codes it."""
    rows = Grade.objects.filter(is_active=True).select_related("level").order_by("level__sort_order", "sort_order", "name")
    return Response([{"slug": g.slug, "name": g.name, "level": g.level.name, "number": g.number} for g in rows])


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    user = s.save()
    return Response({"token": Token.objects.get_or_create(user=user)[0].key, "profile": profile_data(user)}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    username = str(request.data.get("username", "")).strip()
    if lockout.login_blocked(request, username):
        return Response({"detail": "Too many attempts. Try again in 15 minutes."}, status=429)
    user = authenticate(request, username=username, password=str(request.data.get("password", "")))
    if not user:
        lockout.login_failed(request, username)
        return Response({"detail": "Username or password is incorrect."}, status=400)
    lockout.login_ok(request, username)
    return Response({"token": Token.objects.get_or_create(user=user)[0].key, "profile": profile_data(user)})


@api_view(["GET"])
def me(request):
    return Response(profile_data(request.user))


@api_view(["GET"])
def subjects(request):
    return Response(SubjectSerializer(Subject.objects.filter(is_published=True, parent=None), many=True).data)


class FormulaList(generics.ListAPIView):
    serializer_class = FormulaListSerializer

    def get_queryset(self):
        g = self.request.query_params
        qs = search_formulas(g.get("q"), g.get("subject"), g.get("level"), g.get("difficulty"), g.get("topic"), g.get("sort", "relevance"))
        return restrict_queryset(self.request.user, qs).distinct()

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        if page is not None:
            prefetch(page, "subjects", "levels")          # two queries for the whole page instead of two per formula
        return page


@api_view(["GET"])
def formula_detail(request, slug):
    f = get_object_or_404(published().prefetch_related(
        "variables", "derivation_steps", "assumptions", "examples", "formula_references__reference"), slug=slug)
    prefetch([f], "subjects", "levels")
    if not can_view(request.user, f):
        return Response({"detail": "Upgrade to Premium to open this formula.", "code": "upgrade_required"}, status=403)
    return Response(FormulaDetailSerializer(f, context={"request": request}).data)
