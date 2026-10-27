"""URL converter for MongoDB ObjectId primary keys:  path("roles/<objectid:pk>/edit/", ...)"""
from bson import ObjectId
from django.urls import register_converter


class ObjectIdConverter:
    regex = "[0-9a-fA-F]{24}"

    def to_python(self, value):
        return ObjectId(value)

    def to_url(self, value):
        return str(value)


register_converter(ObjectIdConverter, "objectid")
