"""Publishing workflow. All status changes go through transition(); the admin calls it too."""
from django.core.exceptions import PermissionDenied, ValidationError
from django_mongodb_backend import transaction
from django.utils import timezone
from accounts.scope import can_act
from .models import Formula, FormulaRevision, Review, Status as S

ALLOWED = {
    S.DRAFT: {S.SUBMITTED, S.ARCHIVED},
    S.SUBMITTED: {S.IN_REVIEW, S.DRAFT},
    S.IN_REVIEW: {S.APPROVED, S.NEEDS_CORRECTION},
    S.APPROVED: {S.PUBLISHED, S.NEEDS_CORRECTION},
    S.PUBLISHED: {S.NEEDS_CORRECTION, S.ARCHIVED},
    S.NEEDS_CORRECTION: {S.SUBMITTED, S.ARCHIVED},
    S.ARCHIVED: {S.DRAFT},
}
ACTION = {S.DRAFT: "create", S.SUBMITTED: "create", S.ARCHIVED: "create", S.IN_REVIEW: "review",
          S.APPROVED: "review", S.NEEDS_CORRECTION: "review", S.PUBLISHED: "publish"}


def snapshot(f):
    return {"title": f.title, "latex": f.latex, "short_explanation": f.short_explanation,
            "detailed_explanation": f.detailed_explanation, "status": f.status,
            "variables": list(f.variables.values("symbol", "name", "unit", "constraints")),
            "derivation": list(f.derivation_steps.values("step_number", "latex", "explanation"))}


@transaction.atomic
def transition(formula, target, user, notes=""):
    if target not in ALLOWED.get(formula.status, set()):
        raise ValidationError(f"Cannot move from {formula.status} to {target}.")
    if not can_act(user, formula, ACTION[target]):
        raise PermissionDenied("You do not have access to this subject for this action.")
    if ACTION[target] in ("review", "publish") and formula.created_by_id == user.id and not user.is_superuser:
        raise PermissionDenied("You cannot review or publish your own formula.")
    if target == S.PUBLISHED:
        if formula.reviewed_by_id is None:
            raise ValidationError("A reviewed formula is required before publishing.")
        formula.published_at = timezone.now()
    if target in (S.APPROVED, S.NEEDS_CORRECTION):
        formula.reviewed_by = user
        formula.last_reviewed_at = timezone.now()
        Review.objects.create(formula=formula, reviewer=user, notes=notes,
                              decision=Review.Decision.APPROVE if target == S.APPROVED else Review.Decision.CORRECT)
    formula.status = target
    formula.save()
    version = (formula.revisions.first().version + 1) if formula.revisions.exists() else 1
    FormulaRevision.objects.create(formula=formula, version=version, snapshot=snapshot(formula),
                                   changed_by=user, reason=f"{target}: {notes}"[:300])
    return formula
