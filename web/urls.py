from django.urls import path
from django.contrib.sitemaps.views import sitemap
from . import views, views_user as vu
from .sitemaps import SITEMAPS
urlpatterns = [
    path("", views.home, name="home"),
    path("explore/", views.explore, name="explore"),
    path("formulas/<slug:slug>/", views.formula_detail, name="formula_detail"),
    path("subjects/<slug:slug>/", views.subject_page, name="subject"),
    path("subjects/<slug:subject>/<slug:slug>/", views.topic_page, name="topic"),
    path("about/", views.about, name="about"),
    path("img/<uuid:pk>/", views.db_image, name="db_image"),
    path("formulas/<slug:slug>/save/", vu.bookmark_toggle, name="bookmark"),
    path("saved/", vu.saved, name="saved"),
    path("history/", vu.history, name="history"),
    path("practice/", vu.practice, name="practice"),
    path("practice/<objectid:pk>/answer/", vu.practice_answer, name="practice_answer"),
    path("submit/", vu.submit_formula, name="submit_formula"),
    path("submit/<uuid:pk>/", vu.submit_formula, name="submit_edit"),
    path("my-submissions/", vu.my_submissions, name="my_submissions"),
    path("p/<slug:slug>/", vu.static_page, name="static_page"),
    path("robots.txt", vu.robots, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("api/suggest/", views.suggest, name="suggest"),
]
