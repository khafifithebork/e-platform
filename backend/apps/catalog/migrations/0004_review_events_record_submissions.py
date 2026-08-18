"""Rename the review-event fields and admit submissions to the trail.

Hand-written rather than autodetected. `makemigrations` recognised one of the
two renames and proposed dropping the other column and adding a new one, which
is indistinguishable from a rename on an empty table and silently destroys the
review history on a populated one. `RenameField` is `ALTER TABLE ... RENAME
COLUMN`: metadata only, no table rewrite, no lock held for the length of a
scan.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_section_lesson_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="coursereviewevent",
            old_name="reviewer",
            new_name="actor",
        ),
        migrations.RenameField(
            model_name="coursereviewevent",
            old_name="decision",
            new_name="action",
        ),
        migrations.AlterField(
            model_name="coursereviewevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("SUBMITTED", "Submitted for review"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("CHANGES_REQUESTED", "Changes requested"),
                ],
                max_length=20,
            ),
        ),
    ]
