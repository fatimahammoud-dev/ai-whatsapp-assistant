"""A field declared unique=True already gets a btree index. Repeating it in
Meta.indexes creates a second identical index that Postgres must keep in sync
on every write and the planner will never prefer.
"""

import pytest
from django.apps import apps
from django.db import connection

PROJECT_APPS = [
    "accounts",
    "bookings",
    "conversations",
    "core",
    "integrations",
    "tenants",
]

PROJECT_TABLES = sorted(
    model._meta.db_table
    for model in apps.get_models()
    if model._meta.app_label in PROJECT_APPS
)


def index_columns(indexdef):
    """The column list of an index definition, e.g. 'btree (a, b)' -> 'a, b'."""
    return indexdef[indexdef.index("(") + 1 : indexdef.rindex(")")].strip()


@pytest.mark.django_db
@pytest.mark.parametrize("table", PROJECT_TABLES)
def test_no_two_indexes_cover_the_same_columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            [table],
        )
        rows = cursor.fetchall()

    by_columns = {}
    for name, definition in rows:
        # varchar_pattern_ops indexes back LIKE queries and are not duplicates.
        if "_pattern_ops" in definition:
            continue
        by_columns.setdefault(index_columns(definition), []).append(name)

    duplicates = {
        columns: names for columns, names in by_columns.items() if len(names) > 1
    }

    assert duplicates == {}
