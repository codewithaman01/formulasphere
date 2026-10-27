import io
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

MAX_UPLOAD_BYTES = 3 * 1024 * 1024
_FORMATS = {"JPEG": ("image/jpeg", {"quality": 85, "optimize": True}), "PNG": ("image/png", {"optimize": True}),
            "WEBP": ("image/webp", {"quality": 85})}


class StoredImage(models.Model):
    """An uploaded picture kept inside the database (not in a media folder), so one database backup holds everything.
    Pictures are never edited: replacing one creates a new row with a new address, which is why they can be cached for a year."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    data = models.BinaryField()
    content_type = models.CharField(max_length=40)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.content_type} {self.width}x{self.height}"

    @property
    def url(self):
        return reverse("db_image", args=[self.pk])

    @classmethod
    def from_upload(cls, upload, max_px=1024):
        """Checks a JPG, PNG or WebP upload, turns it upright, strips hidden metadata (camera, GPS), shrinks it to
        max_px and stores it. Raises ValidationError with a message a person can read."""
        from PIL import Image, ImageOps, UnidentifiedImageError
        if upload.size > MAX_UPLOAD_BYTES:
            raise ValidationError("This picture is larger than 3 MB. Please choose a smaller one.")
        try:
            img = Image.open(upload)
            fmt = img.format
            if fmt not in _FORMATS:
                raise ValidationError("Use a JPG, PNG or WebP picture.")
            if img.width * img.height > 40_000_000:
                raise ValidationError("This picture is too large in pixels. Please choose a smaller one.")
            img = ImageOps.exif_transpose(img)
            img.thumbnail((max_px, max_px))
            if fmt == "JPEG" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format=fmt, **_FORMATS[fmt][1])
        except ValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise ValidationError("This file could not be read as a picture. Use a JPG, PNG or WebP picture.")
        data = buf.getvalue()
        return cls.objects.create(data=data, content_type=_FORMATS[fmt][0], width=img.width, height=img.height, size=len(data))


def image_url(image_id):
    return reverse("db_image", args=[image_id]) if image_id else ""


class Leader(models.Model):
    """A person shown at the bottom of every page and on the About page (owner, CEO, founder...).
    Everything here is edited by staff in the panel, nothing is typed into templates."""
    name = models.CharField(max_length=120)
    role_title = models.CharField("title", max_length=120, help_text="For example: Owner and CEO, Founder, Head of Content.")
    photo = models.ForeignKey(StoredImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    short_bio = models.CharField(max_length=240, blank=True, help_text="One or two lines shown at the bottom of every page.")
    about = models.TextField(blank=True, help_text="Full message or story shown on the About page. Blank lines make new paragraphs.")
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True, help_text="Starts with https://")
    is_shown = models.BooleanField("shown on the site", default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def photo_url(self):
        return image_url(self.photo_id)        # built from the id, so showing it never loads the picture itself


class LeaderItem(models.Model):
    """One line under a person: a qualification, an achievement, a past role, or anything else."""
    KINDS = [("qualification", "Qualification"), ("achievement", "Achievement"),
             ("experience", "Experience"), ("other", "Other")]
    HEADINGS = {"qualification": "Qualifications", "achievement": "Achievements",
                "experience": "Experience", "other": "More about them"}

    leader = models.ForeignKey(Leader, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=15, choices=KINDS, default="qualification")
    title = models.CharField(max_length=200, help_text="For example: M.Sc. Physics, or Winner of the National Teaching Award.")
    detail = models.TextField(blank=True, help_text="Optional: the school, the organisation, or a sentence about it.")
    year = models.CharField(max_length=20, blank=True, help_text="Optional: 2019 or 2015-2019.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.leader}: {self.title}"

    @property
    def kind_label(self):
        return self.get_kind_display()


class SiteSetting(models.Model):
    """One row only: the site logo and tab icon, uploaded by staff in the admin. Blank means the built-in logo is used."""
    logo = models.ForeignKey(StoredImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    favicon = models.ForeignKey(StoredImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)

    @property
    def logo_url(self):
        return image_url(self.logo_id)

    @property
    def favicon_url(self):
        return image_url(self.favicon_id)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        if self._state.adding and self.pk is None:       # keep a single row: reuse the existing one if there is one
            existing = type(self).objects.order_by("pk").values_list("pk", flat=True).first()
            if existing is not None:
                self.pk = existing
        super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        return cls.objects.order_by("pk").first()


class StaticPage(models.Model):
    """Privacy, Terms, Contact... Edited in the panel under Site pages; nothing is typed into templates."""
    slug = models.SlugField(unique=True, help_text="Used in the address, for example privacy gives /p/privacy/")
    title = models.CharField(max_length=160)
    body = models.TextField(help_text="Blank lines make new paragraphs. A line starting with ## becomes a heading.")
    show_in_footer = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title
