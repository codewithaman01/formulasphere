"""Batch-loading of many-to-many relations.

Django's QuerySet.prefetch_related() cannot load many-to-many fields on MongoDB (the backend refuses the
internal query it uses). prefetch() does the same job: it loads a whole page of objects' related rows in two
queries instead of one query per object, and stores them where `obj.subjects.all()` looks first, so templates and
serializers need no change.

    items = list(queryset)
    prefetch(items, "subjects", "levels")            # many-to-many
    prefetch(items, "topics__subject")               # nested: many-to-many, then a foreign key
    prefetch(items, "variables")                     # other kinds are handed to Django's own prefetch

Returns the same list, so  prefetch(list(qs), "subjects")  can be used in an expression.
"""
from collections import defaultdict

from django.db.models import ManyToManyField, prefetch_related_objects


def prefetch(objs, *lookups):
    objs = [o for o in objs if o is not None]
    if not objs:
        return objs
    for lookup in lookups:
        head, _, rest = lookup.partition("__")
        field = type(objs[0])._meta.get_field(head)
        if isinstance(field, ManyToManyField):
            _many_to_many(objs, field, head, rest)
        else:
            prefetch_related_objects(objs, lookup)     # foreign keys and reverse foreign keys work natively
    return objs


def _many_to_many(objs, field, name, rest):
    through = field.remote_field.through
    src, dst = field.m2m_field_name(), field.m2m_reverse_field_name()
    pks = [o.pk for o in objs]
    pairs = list(through._default_manager.filter(**{f"{src}__in": pks}).values_list(f"{src}_id", f"{dst}_id"))
    by_target = defaultdict(list)
    for s, d in pairs:
        by_target[d].append(s)
    related = field.related_model
    targets = list(related._default_manager.filter(pk__in=list(by_target))) if by_target else []   # in the model's default order
    per_source = defaultdict(list)
    for t in targets:
        for s in by_target[t.pk]:
            per_source[s].append(t)
    for o in objs:
        manager = getattr(o, name)
        qs = manager.get_queryset()
        qs._result_cache = per_source.get(o.pk, [])
        qs._prefetch_done = True
        try:
            cache = o._prefetched_objects_cache
        except AttributeError:
            cache = o._prefetched_objects_cache = {}
        cache[manager.prefetch_cache_name] = qs
    if rest and targets:
        prefetch(targets, rest)
