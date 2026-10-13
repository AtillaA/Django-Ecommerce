# CLAUDE.md

Django ecommerce storefront (multi-vendor grocery-style shop) built from a tutorial template
(Desphixs / "Nest" HTML theme). The store has no real data yet; `seed_test_data` adds disposable
test products, and real content is added via the admin.

## Standing instructions

- **Keep this file current.** After finishing any feature or change, update the relevant
  sections below (feature table, gotchas, functional discrepancies, tested and working). Keep
  entries short and don't describe what the code already makes obvious; record intent,
  decisions and traps.
- **Business importance is the user's call.** The user decides how important a feature is to
  customers; Claude handles the technical side. When a new or changed feature's importance
  is unknown, ask one short question and record the answer in the feature table.
- Ask before changing behaviour of anything marked **critical** in the feature table.
- **Commits:** fold trivial tweaks (copy, placeholders, small styling) into the next related
  commit and mention them in its message; give meaningful or separately-revertible changes
  their own commit. Work on a branch and open a PR unless told otherwise.
- When a functional discrepancy below is fixed, delete its line (and add the feature to
  "Tested and Working" once verified).
- The user works on Windows 11: give Windows (PowerShell/cmd) commands.

## Commands

```powershell
# Windows 11 (PowerShell). macOS/Linux: `source .venv/bin/activate`, `cp` instead of `copy`.
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # required: settings read SECRET_KEY/DEBUG etc. from .env
python manage.py migrate
python manage.py runserver      # http://127.0.0.1:8000
python manage.py createsuperuser   # prompts for email, username, password
python manage.py seed_test_data            # test categories/vendors/products; re-running replaces them
python manage.py seed_test_data --delete   # remove them again

python manage.py check
python manage.py makemigrations --check --dry-run   # must print "No changes detected"
python manage.py test           # tests live in core/, userauths/ and useradmin/tests.py
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
| Customer dashboard: profile, orders, addresses, password (the template's orders chart was removed; the user plans their own) | `core` `customer_dashboard` | ? |
| Wishlist | `core` | ? |
| Reviews and ratings | `core` `ajax_add_review` | ? |
| Store dashboard for superusers | `useradmin` | ? |
| Django admin | `/admin/` | ? |
| Contact form and info pages (about, privacy, terms, purchase guide) | `core` | ? |

## Gotchas

- User data (orders, addresses, wishlist, reviews, profile) must be read and changed only through
  `request.user`: filter querysets by it and fetch single rows with
  `get_object_or_404(Model, id=..., user=request.user)`. The template ignored this everywhere;
  `core/tests.py` `UserIsolationTests` covers the fixed views.
- Products only appear on the storefront when `product_status == "published"` (new ones default
  to `in_review`); the homepage shows only `featured` ones. Publishing is admin-only by design
  (user's decision): products added in the store dashboard stay `in_review` until an admin
  publishes them in `/admin/`, so `AddProductForm` deliberately has no status/featured fields.
- All data is disposable until launch. After model changes that clash with existing rows,
  resetting is fine (PowerShell): `del db.sqlite3; python manage.py migrate; python manage.py seed_test_data`.
- The site is a single store: every product saved without a vendor gets the default vendor
  "Nacar" (`Vendor.default()`, fixed `vid="nacar"`, so renaming it is safe; created by migration
  0027). Templates assume every product has a vendor (`{% url 'core:vendor-detail' p.vendor.vid %}`):
  deleting Nacar would null it on all products (`SET_NULL`) and crash category/search pages.
- `seed_test_data` marks its rows by IDs (`pid`/`cid`) starting with `test-`, which generated
  IDs never do; `--delete` removes only those, plus their gallery images, reviews, wishlist rows,
  unused tags and `media/test-data/` (products use Nacar, which it keeps). Update its `PRODUCTS` list when the
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

## Functional Discrepancies to be Fixed

Found in the template and confirmed against the running app (October 2026 audit, with
`seed_test_data`). Each line is meant to become its own fix and PR; delete it once fixed.

### Priority

#### Blocks shopping/account use

- "Forgot password?" on the sign-in page is `href="#"`: there is no password reset flow (it needs
  an email backend). The dashboard's "Track your order" form posts to `#` (its tab link is
  commented out, so customers can't reach it).

#### Store dashboard


### Major

- Cart quantities aren't validated: negative values give negative totals; an empty value makes
  `/update-cart/` fail (500) and hides the refresh button; adding an item already in the cart
  replaces its quantity instead of adding to it.
- Stock is never checked when adding to cart or ordering, and orders don't reduce it
  (`in_stock`/`stock_count` unused in views).
- `Product.get_precentage` returns the price as a % of `old_price` (83 for 9.99/11.99), but
  templates show it as the discount ("-83% Off").
- Nothing sends email: contact messages are only stored (`ContactUs`, visible in `/admin/`); no
  order confirmations.

### Minor

- Dead-end routes, labelled for the dead-ends pass. Theme links are relative, so they 404 under
  whatever page they sit on (e.g. `/product/test-01/shop-compare.html`). Counts skip commented-out
  markup and the store dashboard (October 2026):

  | Dead link | Links | Where / what | Likely fix |
  |---|---|---|---|
  | `shop-product-right.html` | 191 | Demo product cards in `core/index.html` (152); sidebar demo products on vendor, shop, search, tag pages | Remove with the demo blocks |
  | `shop-grid-right.html` | 117 | Category labels on product cards (incl. `async/product-list.html`); sidebars of info pages and the product page | `core:category-product-list` / `core:product-list` |
  | `vendor-details-1.html` | 81 | "By (vendor)" on demo product cards | Remove with the demo blocks |
  | `vendor-details-2.html` | 2 | Vendor name on the product page | `core:vendor-detail` |
  | `shop-cart.html` | 81 | "Add" on demo product cards | Remove with the demo blocks |
  | `shop-compare.html` | 62 | "Compare" icons | Remove (no compare feature) or build one |
  | `shop-wishlist.html` | 61 | "Add To Wishlist" icons on demo cards | Remove with the demo blocks |
  | `shop-product-detail.html` | 15 | Demo products in info-page and product-page sidebars | Remove |
  | `index.html` | 20 | Breadcrumb "Home" on 20 pages | `core:index` |
  | `page-login.html` | 3 | "Logout" in the dashboard and profile-edit menus; "Log in instead!" on order detail | `userauths:sign-out` / remove |
  | `page-register.html` | 1 | "Register now" on the product page | `userauths:sign-up` |
  | `page-contact.html` | 1 | "contact us" on the terms page | `core:contact` |
  | `/cdn-cgi/l/email-protection` | 1 | Footer email, shows "[email protected]" (Cloudflare leftover) | Real `mailto:` |
  | `#` | 225 | 97 in `partials/base.html`: every "Mega menu" entry, language/currency switchers, footer columns (Delivery Information, Support Center, Careers, ...), social icons; the rest are placeholders in page templates (vendor/about demo links, pagination) | Link real pages or remove |

  "Deals" in the main menu opens the full shop (no deals page).
- Most of `core/index.html` is fixed demo content: only the first "Popular Products" tab and
  "Shop by Categories" use real data. "Deals Of The Day", "Top Selling", "Trending Products",
  "Recently added", "Top Rated" and the other tabs are demo products whose 60 "Add" buttons link
  to `shop-cart.html` (404). Hardcoded "Milks & Dairies" labels on the category sidebar
  (~line 3006).
- "Quick view" buttons (61) target a `#quickViewModal` that doesn't exist.
- Mobile search doesn't search (`partials/base.html` ~line 393: `action="#"`, input has no
  `name`); the header search's category dropdown is demo data and ignored.
- Newsletter "Subscribe" forms have no backend.
- Shop page "Show"/"Sort by" dropdowns do nothing; no pagination (it is commented out).
- The product page "Delivery" box labels the default address "Verified Address" and others
  "Unverified Address" (it only reflects the default flag).
- Other leftover content: "Desphixs" branding (`JAZZMIN_SETTINGS`, footer in
  `partials/base.html`), "Nestify" default vendor name, hardcoded breadcrumb and "(32 reviews)"
  on `core/product-detail.html`, fallback avatars hotlinked from external sites.
- Missing static files: preloader image tag is malformed (`partials/base.html` ~line 686),
  relative `favicon.svg` and `slider-range.css` paths (404 on most pages),
  `assets/imgs/page/contact-2.png`, `assets/imgs/theme/icons/logo-{apple,facebook,google}.svg`,
  and a dead Cloudflare `email-decode.min.js` reference.
- Cart prices come from the browser: `add_to_cart` trusts `price`/`title` GET params, and orders
  are built from them. Must be fixed before taking real orders.
- With `PAYMENT_MOCK` off, `payment_completed_view` marks an order paid on visit without
  verifying the Stripe payment.
- Checkout JS uses `stripe.redirectToCheckout` (deprecated by Stripe) and a PayPal SDK
  `client-id=test`.
- State-changing actions use GET without CSRF (cart, wishlist, default address, contact form,
  `useradmin` product delete); `change_order_status` is `csrf_exempt`.
- Debug `print()` calls throughout the views; `save_checkout_info` prints customer details to the
  server log. Most features have no tests.

## Tested and Working

Confirmed in the October 2026 audit (browser and test client, with `seed_test_data`):

- Sign-up and sign-in (a wrong password says "Wrong password"; `?next=` is followed only within
  this site); sign-out shows "Signed-out successfully" on the home page.
- Signed-out visitors are sent to sign in (and back) instead of getting errors: order and profile
  pages redirect; wishlist, review and address actions answer 401 (`ajax_login_required`) and
  `function.js` redirects.
- Browsing: home, shop, categories, vendors, tags and product pages (with image gallery).
- Header search; results and "related products" show only published products (`/search/` without
  a term lists them all).
- Store-dashboard revenue: "Revenue" sums paid orders; "Monthly Earning" is this month of this
  year, paid only.
- Store-dashboard product tags: "breakfast, sweet" saves two tags (taggit `TagField`), shown back
  the same way when editing; tags are optional.
- Products without a chosen vendor (store dashboard, admin) get Nacar and show on category,
  search and vendor pages.
- Shop filters: category, vendor and price, alone or combined (none ticked lists everything).
- Add to cart from product lists (including filtered results) and the product page (quantity
  respected).
- Cart page: removing lines and changing quantities redraw it in place (no reload), keeping
  anything typed in the checkout details; "Proceed To CheckOut" then works.
- Wishlist add and remove, with the header count updating live; the wishlist page lists only your own items, and removing someone
  else's item by ID gives 404.
- Reviews when signed in.
- Contact form (message saved).
- Profile edit (`/user/profile/update/`: name, bio, phone, image) updates the signed-in user's
  profile only.
- Password change in the dashboard's "Account details" tab: current password, new password
  twice (Django's password rules); errors reopen the tab; success says "Password changed
  successfully", keeps the user signed in and shows the Profile tab. The store dashboard's
  password page works the same way (same form and rules, hidden inputs) and goes to "Profile
  setting".
- Adding addresses and setting a default (only your own addresses change); the product page
  "Delivery" box shows the default address (else the newest), or a sign-in/no-address prompt.
- Order history and order detail in the customer dashboard.
- Unknown products, categories, vendors and orders (storefront and store dashboard) give 404,
  and so does another user's order.
- Checkout with the mock payment (`core/tests.py` covers it). With `PAYMENT_MOCK=False`,
  `create_checkout_session` (Stripe) needs POST, sign-in, CSRF and the user's own unpaid order,
  and never resets `paid_status` (tested with Stripe mocked; no real Stripe run yet).
