from django.urls import path
from . import views
urlpatterns = [
    path("account-types/", views.account_types),
    path("grades/", views.grades),
    path("auth/register/", views.register),
    path("auth/login/", views.login),
    path("me/", views.me),
    path("subjects/", views.subjects),
    path("formulas/", views.FormulaList.as_view()),
    path("formulas/<slug:slug>/", views.formula_detail),
]
