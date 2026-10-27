from django.urls import path
from . import views
urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("premium/", views.pricing, name="pricing"),
    path("premium/<slug:slug>/choose/", views.plan_choose, name="plan_choose"),
    path("premium/requests/<objectid:pk>/reference/", views.plan_reference, name="plan_reference"),
    path("premium/requests/<objectid:pk>/cancel/", views.plan_cancel, name="plan_cancel"),
    path("premium/requests/<objectid:pk>/pay/", views.pay_start, name="pay_start"),
    path("premium/requests/<objectid:pk>/verify/", views.pay_verify, name="pay_verify"),
    path("hooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
