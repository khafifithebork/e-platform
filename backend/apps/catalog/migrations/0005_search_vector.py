"""The stored search vector, its GIN index, and the trigram extension.

Invariant 14, both halves:

- **`CREATE INDEX CONCURRENTLY`** on a populated table, via
  `AddIndexConcurrently`. `catalog_course` holds published rows and a plain
  `CREATE INDEX` takes an `ACCESS EXCLUSIVE` lock for its duration — every read
  of the catalogue blocks behind it. Concurrent building costs a second table
  pass and blocks nothing.
- **No backfill here.** The column lands null and stays null;
  `backfill_search_vectors` fills it in chunks. A migration that populated
  every row would hold one transaction open across the whole table, which is
  the lock this file is written to avoid.

`atomic = False` is required, not stylistic: PostgreSQL refuses
`CREATE INDEX CONCURRENTLY` inside a transaction block, and Django wraps every
migration in one by default.

**The trade that comes with it.** A non-atomic migration cannot roll back. If
this fails halfway the index may exist as `INVALID` and must be dropped by
hand before retrying — that is the documented cost of not locking the table,
and it is the right way round for a table learners read.

`TrigramExtension` is here rather than in T3 so that a missing `CREATE
EXTENSION` privilege fails at the migration that installs it rather than at the
query that needs it. **Unverified on Neon:** the local container runs as a
superuser and a managed provider may not grant this.
"""

import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.contrib.postgres.operations import AddIndexConcurrently, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0004_review_events_record_submissions"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddField(
            model_name="course",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(editable=False, null=True),
        ),
        AddIndexConcurrently(
            model_name="course",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="course_search_vector_gin"
            ),
        ),
    ]
