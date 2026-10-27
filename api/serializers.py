from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from accounts.access import can_view
from accounts.models import AccountType, Profile
from formulas.models import Assumption, DerivationStep, Example, Formula, FormulaReference, FormulaVariable
from taxonomy.models import Grade, Subject

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    account_type = serializers.SlugRelatedField(slug_field="slug", queryset=AccountType.objects.filter(is_active=True),
                                                required=False)   # omitted = "student", for older app versions
    grade = serializers.CharField(max_length=20, required=False, allow_blank=True)   # a Grade slug, checked below

    def validate_username(self, v):
        if User.objects.filter(username__iexact=v).exists():
            raise serializers.ValidationError("That username is taken.")
        return v

    def validate(self, a):
        t = a.get("account_type") or AccountType.objects.filter(slug=settings.DEFAULT_ACCOUNT_TYPE, is_active=True).first()
        if t is None:
            raise serializers.ValidationError({"account_type": "Choose an account type."})
        if t.asks_grade:
            if not a.get("grade") or not Grade.objects.filter(slug=a["grade"], is_active=True).exists():
                raise serializers.ValidationError({"grade": "Select your grade."})
        else:
            a["grade"] = t.default_grade
        a["account_type"] = t
        try:
            validate_password(a["password"], User(username=a["username"], email=a["email"]))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": e.messages})
        return a

    def create(self, d):
        user = User.objects.create_user(username=d["username"], email=d["email"], password=d["password"])
        Profile.objects.create(user=user, account_type=d["account_type"], grade=d["grade"],
                               trial_ends_at=timezone.now() + timedelta(days=settings.TRIAL_DAYS))
        return user


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["slug", "name", "description", "icon"]


class FormulaListSerializer(serializers.ModelSerializer):
    subjects = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    levels = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Formula
        fields = ["slug", "title", "latex", "short_explanation", "difficulty", "access_tier", "min_class",
                  "subjects", "levels", "source_verification", "is_demo", "locked"]

    def get_locked(self, f):
        return not can_view(self.context["request"].user, f)


class _Var(serializers.ModelSerializer):
    class Meta:
        model = FormulaVariable
        fields = ["symbol", "name", "meaning", "unit", "constraints"]


class _Step(serializers.ModelSerializer):
    class Meta:
        model = DerivationStep
        fields = ["step_number", "latex", "explanation"]


class _Assumption(serializers.ModelSerializer):
    class Meta:
        model = Assumption
        fields = ["description", "validity"]


class _Example(serializers.ModelSerializer):
    class Meta:
        model = Example
        fields = ["title", "problem", "given", "solution", "result", "units"]


class _Ref(serializers.ModelSerializer):
    title = serializers.CharField(source="reference.title")
    authors = serializers.CharField(source="reference.authors")
    year = serializers.IntegerField(source="reference.year")
    doi = serializers.CharField(source="reference.doi")
    url = serializers.CharField(source="reference.url")

    class Meta:
        model = FormulaReference
        fields = ["title", "authors", "year", "doi", "url", "locator"]


class FormulaDetailSerializer(FormulaListSerializer):
    variables = _Var(many=True, read_only=True)
    derivation_steps = _Step(many=True, read_only=True)
    assumptions = _Assumption(many=True, read_only=True)
    examples = _Example(many=True, read_only=True)
    references = _Ref(source="formula_references", many=True, read_only=True)

    class Meta(FormulaListSerializer.Meta):
        fields = FormulaListSerializer.Meta.fields + [
            "detailed_explanation", "last_reviewed_at", "variables", "derivation_steps",
            "assumptions", "examples", "references"]
