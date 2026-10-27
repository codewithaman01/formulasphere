from django.urls import path
from . import views

app_name = "learning"
urlpatterns = [
    path("courses/", views.courses, name="courses"),
    path("courses/<slug:slug>/", views.course_detail, name="course"),
    path("courses/<slug:slug>/enroll/", views.enroll, name="enroll"),
    path("live/", views.live_list, name="live"),
    path("live/<slug:slug>/", views.live_detail, name="live_detail"),
    path("live/<slug:slug>/register/", views.live_register, name="live_register"),
    path("live/<slug:slug>/cancel/", views.live_unregister, name="live_unregister"),
    path("tuition/", views.tuition, name="tuition"),
    path("my-learning/", views.my_learning, name="my"),
]
