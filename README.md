# Django-Ecommerce
Ecommerce website template built in Django web framework.

## Run locally

Requires Python 3.10+ (tested with 3.14).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python manage.py migrate
python manage.py createsuperuser # log in with the email address + password
python manage.py runserver
```

- Storefront: http://127.0.0.1:8000/
- Store dashboard (superusers): http://127.0.0.1:8000/useradmin/
- Django admin: http://127.0.0.1:8000/admin/

The store starts empty. Add categories, vendors and products from the Django admin.
Card (Stripe) and PayPal payments won't work until their keys are set in `.env`.
