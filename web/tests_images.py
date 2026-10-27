"""python manage.py test web.tests_images   -- pictures are stored in the database, not in a media folder"""
import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from .models import Leader, SiteSetting, StoredImage


def png(w=800, h=600, color="red", fmt="PNG"):
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, fmt); return b.getvalue()


def boss():
    u = get_user_model().objects.create_superuser("boss", "b@example.com", "pw-Str0ng-pass")
    c = Client(); c.login(username="boss", password="pw-Str0ng-pass"); return c


class DatabaseImageTests(TestCase):
    def test_logo_upload_is_stored_in_database_and_served(self):
        c = boss()
        r = c.post("/panel/logo/", {"logo_upload": SimpleUploadedFile("logo.png", png(1500, 900), "image/png")})
        self.assertEqual(r.status_code, 302)
        img = SiteSetting.current().logo
        self.assertEqual(img.content_type, "image/png"); self.assertLessEqual(max(img.width, img.height), 512)
        resp = Client().get(img.url)                                    # public: the header logo needs no sign-in
        self.assertEqual(resp.status_code, 200); self.assertEqual(resp["Content-Type"], "image/png")
        self.assertIn("immutable", resp["Cache-Control"])
        self.assertEqual(Client().get(img.url, HTTP_IF_NONE_MATCH=resp["ETag"]).status_code, 304)
        self.assertIn(img.url, Client().get("/").content.decode())     # shown in the page header

    def test_replace_and_remove_delete_old_picture(self):
        c = boss()
        c.post("/panel/logo/", {"logo_upload": SimpleUploadedFile("a.png", png(), "image/png")})
        first = SiteSetting.current().logo_id
        c.post("/panel/logo/", {"logo_upload": SimpleUploadedFile("b.png", png(color="blue"), "image/png")})
        second = SiteSetting.current().logo_id
        self.assertNotEqual(first, second); self.assertFalse(StoredImage.objects.filter(pk=first).exists())
        c.post("/panel/logo/", {"remove_logo": "on"})
        self.assertIsNone(SiteSetting.current().logo_id); self.assertEqual(StoredImage.objects.count(), 0)

    def test_bad_files_are_refused(self):
        c = boss()
        for name, data in [("x.png", b"not an image at all"), ("big.png", png() + b"0" * (3 * 1024 * 1024)),
                           ("evil.png", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>")]:
            r = c.post("/panel/logo/", {"logo_upload": SimpleUploadedFile(name, data, "image/png")})
            self.assertEqual(r.status_code, 200, name)                  # form shown again with an error
        self.assertEqual(StoredImage.objects.count(), 0)

    def test_metadata_is_stripped_and_photo_is_resized(self):
        b = io.BytesIO(); im = Image.new("RGB", (2000, 1000), "green")
        exif = Image.Exif(); exif[0x010F] = "SecretCameraMaker"; im.save(b, "JPEG", exif=exif)
        c = boss()
        c.post("/panel/c/leaders/new/", {"name": "Asha", "role_title": "Owner", "is_shown": "on", "sort_order": 0,
                                            "photo_upload": SimpleUploadedFile("p.jpg", b.getvalue(), "image/jpeg")})
        leader = Leader.objects.get(); data = bytes(leader.photo.data)
        self.assertNotIn(b"SecretCameraMaker", data)
        self.assertLessEqual(leader.photo.width, 600)
        self.assertIn(leader.photo_url, Client().get("/about/").content.decode())
        self.assertIn(leader.photo_url, Client().get("/").content.decode())     # footer

    def test_no_media_folder_is_used(self):
        with tempfile.TemporaryDirectory() as d, override_settings(MEDIA_ROOT=d):
            boss().post("/panel/logo/", {"logo_upload": SimpleUploadedFile("a.png", png(), "image/png")})
            self.assertEqual(list(Path(d).rglob("*")), [])
