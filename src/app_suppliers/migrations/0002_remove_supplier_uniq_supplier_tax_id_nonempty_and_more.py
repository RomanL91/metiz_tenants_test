from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("app_suppliers", "0001_initial"),
    ]

    operations = [
        # 1) Безопасно убираем условный уникальный констрейнт (если был)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="supplier",
                    name="uniq_supplier_tax_id_nonempty",
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE app_suppliers_supplier
                        DROP CONSTRAINT IF EXISTS uniq_supplier_tax_id_nonempty;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
        # 2) Безопасно убираем колонку tax_id
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="supplier",
                    name="tax_id",
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE app_suppliers_supplier
                        DROP COLUMN IF EXISTS tax_id CASCADE;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
