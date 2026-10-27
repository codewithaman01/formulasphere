from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from taxonomy.models import Subject
from .models import StaticPage


class StaticViewSitemap(Sitemap):
    """Only public pages. Formula and topic pages need a sign-in, so search engines cannot read them."""
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return ["home", "explore", "about", "pricing", "learning:courses", "learning:live", "learning:tuition"]

    def location(self, name):
        return reverse(name)


class SubjectSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return Subject.objects.filter(is_published=True)

    def lastmod(self, s):
        return s.updated_at

    def location(self, s):
        return reverse("subject", args=[s.slug])


class PageSitemap(Sitemap):
    priority = 0.3

    def items(self):
        return StaticPage.objects.filter(is_published=True)

    def lastmod(self, p):
        return p.updated_at

    def location(self, p):
        return reverse("static_page", args=[p.slug])


SITEMAPS = {"pages": StaticViewSitemap, "subjects": SubjectSitemap, "info": PageSitemap}
