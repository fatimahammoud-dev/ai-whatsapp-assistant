"""Django 6 allows CharField without max_length, which maps to an unbounded
varchar. Unbounded columns cannot be indexed past Postgres' 2704-byte btree
limit, so an oversized value from an external API fails at INSERT rather than
at validation.
"""

import pytest
from django.apps import apps
from django.db import models

PROJECT_APPS = [
    "accounts",
    "bookings",
    "conversations",
    "core",
    "integrations",
    "tenants",
]

CHAR_FIELDS = [
    (f"{model._meta.app_label}.{model.__name__}", field)
    for model in apps.get_models()
    if model._meta.app_label in PROJECT_APPS
    for field in model._meta.get_fields()
    if isinstance(field, models.CharField) and not isinstance(field, models.TextField)
]


@pytest.mark.parametrize(
    ("label", "field"),
    CHAR_FIELDS,
    ids=[f"{label}.{field.name}" for label, field in CHAR_FIELDS],
)
def test_char_fields_declare_a_max_length(label, field):
    assert field.max_length is not None, f"{label}.{field.name} has no max_length"
