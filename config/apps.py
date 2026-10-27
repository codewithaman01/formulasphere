"""MongoDB-aware app configs for Django's built-in apps (they default to integer primary keys, which MongoDB does not have)."""
from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig

_OBJECT_ID = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAdminConfig(AdminConfig):
    default_auto_field = _OBJECT_ID


class MongoAuthConfig(AuthConfig):
    default_auto_field = _OBJECT_ID


class MongoContentTypesConfig(ContentTypesConfig):
    default_auto_field = _OBJECT_ID
