# CLAUDE.md

Django ecommerce storefront (multi-vendor grocery-style shop) built from a tutorial template
(Desphixs / "Nest" HTML theme). The store has no real data yet; `seed_test_data` adds disposable
test products, and real content is added via the admin.

## Standing instructions

- **Keep this file current.** After finishing any feature or change, update the relevant
  sections below (feature table, gotchas, known issues). Keep entries short and don't describe
  what the code already makes obvious; record intent, decisions and traps.
- **Business importance is the user's call.** The user decides how important a feature is to
  customers; Claude handles the technical side. When a new or changed feature's importance
  is unknown, ask one short question and record the answer in the feature table.
- Ask before changing behaviour of anything marked **critical** in the feature table.
- **Commits:** fold trivial tweaks (copy, placeholders, small styling) into the next related
  commit and mention them in its message; give meaningful or separately-revertible changes
  their own commit. Work on a branch and open a PR unless told otherwise.
- When a known issue below is fixed, delete its line.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # required: settings read SECRET_KEY/DEBUG etc. from .env
python manage.py migrate
python manage.py runserver      # http://127.0.0.1:8000
python manage.py createsuperuser   # prompts for email, username, password
python manage.py seed_test_data            # test categories/vendors/products; re-running replaces them
python manage.py seed_test_data --delete   # remove them again

python manage.py check
python manage.py makemigrations --check --dry-run   # must print "No changes detected"
python manage.py test           # tests live in core/tests.py; other apps have none yet
```

Python 3.10+ (tested on 3.14), Django 5.2 LTS, SQLite in development.

## Layout

| Path | What it is |
|---|---|
| `ecomprj/` | Project package: `settings.py` (env-driven via `environs`), `urls.py`, `apps.py` (PayPal IPN app config shim) |
| `core/` | Storefront: products, categories, vendors, tags, reviews, wishlist, session cart, checkout/payments, coupons, customer dashboard, info pages. `context_processor.py` injects categories, vendors, wishlist, address and price range into every template |
| `userauths/` | Custom `User` (login by **email**), `Profile` (auto-created by a `post_save` signal), `ContactUs`; sign-up/in/out, profile edit |
| `useradmin/` | Superuser-only store dashboard at `/useradmin/` (`@admin_required` decorator); product CRUD, orders, reviews, settings. No models |
| `templates/` | All templates (project-level `DIRS`). `partials/base.html` = storefront layout; `useradmin/base.html` = dashboard layout; `core/async/` = HTML fragments returned as JSON to AJAX calls |
| `static/assets/` | Storefront theme (CSS/JS/images/SASS sources). `js/function.js` holds the custom AJAX (cart, filter, wishlist, reviews, contact form) |
| `static/assets2/` | Store dashboard theme |

URLs: storefront at `/`, auth at `/user/`, store dashboard at `/useradmin/`, Django admin (Jazzmin theme) at `/admin/`.

## Features and business importance

Importance is set by the user (customer point of view). `?` = not rated yet: ask.

| Feature | Where | Importance |
|---|---|---|
| Product catalogue: list, detail, category, vendor, tag, search, filter | `core` | ? |
| Cart (stored in the session) | `core` `add_to_cart` / `cart_view` | ? |
| Checkout and payments: mock provider in development, Stripe Checkout/PayPal buttons otherwise, coupons | `core` `checkout`, `mock_payment`, `create_checkout_session` | ? |
| Accounts: sign up/in with email, profile | `userauths` | ? |
| Customer dashboard: orders, addresses | `core` `customer_dashboard` | ? |
| Wishlist | `core` | ? |
| Reviews and ratings | `core` `ajax_add_review` | ? |
| Store dashboard for superusers | `useradmin` | ? |
| Django admin | `/admin/` | ? |
| Contact form and info pages (about, privacy, terms, purchase guide) | `core` | ? |

## Gotchas

- Products only appear on the storefront when `product_status == "published"` (new ones default
  to `in_review`); the homepage shows only `featured` ones.
- All data is disposable until launch. After model changes that clash with existing rows,
  resetting is fine: `rm db.sqlite3 && python manage.py migrate && python manage.py seed_test_data`.
- `seed_test_data` marks its rows by IDs (`pid`/`cid`/`vid`) starting with `test-`, which
  generated IDs never do; `--delete` removes only those, plus their gallery images, reviews,
  wishlist rows, unused tags and `media/test-data/`. Update its `PRODUCTS` list when the
  Product model changes (`core/tests.py` fails if it breaks).
- Deleting a product any other way (e.g. in the admin) leaves its wishlist rows with
  `product=None`, which makes `/wishlist/` return 500. Delete those rows too.
- `.env` is git-ignored and required. `SECRET_KEY` has no default; `DEBUG` defaults to False. The
  old hard-coded secret key is public in git history: never use it in production.
- Payments are mocked while `PAYMENT_MOCK` is on (defaults to `DEBUG`; settings refuse it with
  `DEBUG` off). Checkout then shows one "test payment" button; `core/payments.py` sends the
  order's customer details and amount to a fake provider that always approves, the order is
  marked paid (reference `mock_…` stored in `stripe_payment_intent`) and the cart is emptied.
  The site never collects card details; a real provider must take them on its own hosted page.
- With `PAYMENT_MOCK=False` the Stripe/PayPal buttons return; they need `STRIPE_*`,
  `PAYPAL_RECEIVER_EMAIL` and `PAYPAL_TEST` in `.env`.
- `ecomprj/apps.py` pins django-paypal's IPN app to `AutoField`. Without it, `makemigrations`
  tries to write a migration into the installed package.
- `core/migrations/0010` was edited to use `models.TextField` instead of the retired
  `ckeditor_uploader` field. Don't reinstall django-ckeditor (CKEditor 4); rich text uses
  `django-ckeditor-5`.
- Model image defaults (`product.jpg`, `category.jpg`, `vendor.jpg`) don't exist in `media/`,
  so items without uploads show broken images. `media/` (uploads) is git-ignored.
- Templates only load the `static` and `humanize` tag libraries.
- Deployment isn't set up: `Procfile` (gunicorn) and `runtime.txt` exist, but static file serving
  (e.g. WhiteNoise), a production database and production `.env` values are still missing.

## Known issues (inherited from the template; fix before taking real orders)

- Cart prices come from the browser: `add_to_cart` trusts `price`/`title` GET params, and
  orders are built from them.
- With `PAYMENT_MOCK` off, `payment_completed_view` marks an order paid on visit without
  verifying the Stripe payment.
- `create_checkout_session` is `csrf_exempt` with no sign-in or ownership check, and resets
  `paid_status` to False on whatever order ID it is given.
- Missing ownership checks: `wishlist_view` lists every user's wishlist; `remove_wishlist` and
  `make_address_default` (resets **all** users' addresses) act on any ID.
- State-changing actions use GET without CSRF (cart, wishlist, default address, contact form);
  `change_order_status` is `csrf_exempt`.
- Views crash for anonymous users instead of redirecting: `ajax_add_review`, `add_to_wishlist`,
  `order_detail`. Many views use `.get()` without 404 handling.
- `filter_product`: the `else` branches reset the queryset, so price and category filters are
  dropped unless both a category and a vendor are selected.
- Login/sign-up redirect to an unvalidated `next` parameter.
- `Product.get_precentage` returns the price as a % of `old_price` (83 for 9.99/11.99), but
  templates show it as the discount ("-83% Off").
- Checkout JS uses `stripe.redirectToCheckout` (deprecated by Stripe) and a PayPal SDK
  `client-id=test`.
- Leftover template content: "Desphixs" branding (`JAZZMIN_SETTINGS`, footer in
  `partials/base.html`), "Nestify" default vendor name, large static demo sections in
  `core/index.html` (including hardcoded "Milks & Dairies" labels on the homepage category
  sidebar, ~line 3006, and demo tab names), hardcoded breadcrumb and "(32 reviews)" on
  `core/product-detail.html`, fallback avatars hotlinked from external sites.
- Missing static files: preloader image tag is malformed (`partials/base.html` ~line 686),
  `assets/imgs/page/contact-2.png`, `assets/imgs/theme/icons/logo-{apple,facebook,google}.svg`,
  and a dead Cloudflare `email-decode.min.js` reference.
- Debug `print()` calls throughout the views; `save_checkout_info` prints customer details to
  the server log. Most features have no tests.
