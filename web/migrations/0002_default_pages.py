from django.db import migrations


def add_pages(apps, schema_editor):
    from web.default_pages import PAGES
    StaticPage = apps.get_model("web", "StaticPage")
    for p in PAGES:
        StaticPage.objects.get_or_create(slug=p["slug"], defaults=dict(
            title=p["title"], body=p["body"], sort_order=p["sort_order"], show_in_footer=True, is_published=True))


class Migration(migrations.Migration):
    dependencies = [("web", "0001_initial")]
    operations = [migrations.RunPython(add_pages, migrations.RunPython.noop)]
