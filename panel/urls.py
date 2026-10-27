from django.urls import path
from . import views

app_name = "panel"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # formulas
    path("formulas/", views.formulas, name="formulas"),
    path("formulas/new/", views.formula_edit, name="formula_new"),
    path("formulas/<uuid:pk>/", views.formula_view, name="formula_view"),
    path("formulas/<uuid:pk>/edit/", views.formula_edit, name="formula_edit"),
    path("formulas/<uuid:pk>/move/", views.formula_move, name="formula_move"),
    # subjects, topics, snippets, references share one set of views
    path("c/<str:key>/", views.crud_list, name="crud_list"),
    path("c/<str:key>/new/", views.crud_edit, name="crud_new"),
    path("c/<str:key>/<str:pk>/edit/", views.crud_edit, name="crud_edit"),
    path("c/<str:key>/<str:pk>/delete/", views.crud_delete, name="crud_delete"),
    # site logo and tab icon
    path("logo/", views.branding, name="branding"),
    # students
    path("students/", views.students, name="students"),
    path("students/<objectid:pk>/grant/", views.student_grant, name="student_grant"),
    # roles and staff
    path("roles/", views.roles, name="roles"),
    path("roles/new/", views.role_edit, name="role_new"),
    path("roles/<objectid:pk>/edit/", views.role_edit, name="role_edit"),
    path("roles/<objectid:pk>/delete/", views.role_delete, name="role_delete"),
    path("staff/", views.staff, name="staff"),
    path("staff/new/", views.staff_edit, name="staff_new"),
    path("staff/<objectid:pk>/edit/", views.staff_edit, name="staff_edit"),
    path("staff/<objectid:pk>/delete/", views.staff_delete, name="staff_delete"),
    path("staff/<objectid:pk>/toggle/", views.staff_toggle, name="staff_toggle"),
    path("staff/<objectid:pk>/reset-2fa/", views.staff_reset2fa, name="staff_reset2fa"),
    # activity log and two-factor
    path("audit/", views.audit, name="audit"),
    path("security/", views.security, name="security"),
]
