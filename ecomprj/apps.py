from django.apps import AppConfig


class PayPalIPNConfig(AppConfig):
    # django-paypal ships no AppConfig, so its models would inherit the
    # project's DEFAULT_AUTO_FIELD (BigAutoField) and `makemigrations` would try
    # to write a migration inside the installed package. Pin the field type the
    # package's own migrations use.
    name = "paypal.standard.ipn"
    label = "ipn"
    default_auto_field = "django.db.models.AutoField"
