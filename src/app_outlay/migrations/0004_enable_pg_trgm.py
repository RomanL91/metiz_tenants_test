from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("app_outlay", "0003_estimate_source_file_estimate_source_sheet_index"),
    ]

    operations = [
        TrigramExtension(),
    ]
