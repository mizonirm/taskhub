from django.db import migrations


def make_superusers_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True).update(role="admin", is_email_verified=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_otp_attempts_user_otp_created_at")]
    operations = [migrations.RunPython(make_superusers_admins, migrations.RunPython.noop)]
