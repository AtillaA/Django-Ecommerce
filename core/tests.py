import shutil
from decimal import Decimal
from unittest import mock
import tempfile
from io import StringIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from taggit.models import Tag

from core.models import Address, CartOrder, CartOrderProducts, Category, Product, Vendor, wishlist_model
from userauths.models import User


# Smallest valid GIF, for image uploads in tests.
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"

def cart_of(**quantities):
    """A session cart holding the given quantities of real products, by title."""
    return {str(Product.objects.get(title=title).id): {"qty": qty} for title, qty in quantities.items()}


@override_settings(PAYMENT_MOCK=True)
class MockPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.order = CartOrder.objects.create(user=self.user, price="3.00", full_name="Buyer", email="buyer@example.com")
        Product.objects.create(title="Test Apple", price="1.50", product_status="published")
        self.pay_url = reverse("core:mock-payment", args=[self.order.oid])
        self.client.force_login(self.user)

    def set_cart(self, cart):
        session = self.client.session
        session["cart_data_obj"] = cart
        session.save()

    def assert_paid(self, paid):
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_status, paid)

    def test_checkout_info_creates_order_and_shows_mock_pay_button(self):
        self.set_cart(cart_of(**{"Test Apple": 2}))
        response = self.client.post(reverse("core:save_checkout_info"), {"full_name": "Buyer", "email": "buyer@example.com"})

        order = CartOrder.objects.exclude(pk=self.order.pk).get(user=self.user)
        self.assertRedirects(response, reverse("core:checkout", args=[order.oid]), fetch_redirect_response=False)
        self.assertEqual(CartOrderProducts.objects.get(order=order).total, 3)
        page = self.client.get(response.url)
        self.assertContains(page, reverse("core:mock-payment", args=[order.oid]))
        self.assertNotContains(page, "js.stripe.com")

    def test_checkout_info_without_cart_goes_back_to_cart(self):
        response = self.client.post(reverse("core:save_checkout_info"))
        self.assertRedirects(response, reverse("core:cart"), fetch_redirect_response=False)
        response = self.client.get(reverse("core:save_checkout_info"))
        self.assertRedirects(response, reverse("core:cart"), fetch_redirect_response=False)

    def test_checkout_info_requires_sign_in(self):
        self.client.logout()
        response = self.client.post(reverse("core:save_checkout_info"))
        self.assertTrue(response.url.startswith(reverse("userauths:sign-in")))

    def test_pay_marks_order_paid_and_empties_cart(self):
        self.set_cart(cart_of(**{"Test Apple": 2}))
        response = self.client.post(self.pay_url)

        self.assertRedirects(response, reverse("core:payment-completed", args=[self.order.oid]))
        self.assert_paid(True)
        self.assertTrue(self.order.stripe_payment_intent.startswith("mock_"))
        self.assertNotIn("cart_data_obj", self.client.session)

    def test_get_does_not_pay(self):
        response = self.client.get(self.pay_url)
        self.assertRedirects(response, reverse("core:checkout", args=[self.order.oid]))
        self.assert_paid(False)

    def test_pay_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.pay_url).status_code, 403)
        self.assert_paid(False)

    def test_pay_requires_sign_in(self):
        self.client.logout()
        response = self.client.post(self.pay_url)
        self.assertTrue(response.url.startswith(reverse("userauths:sign-in")))
        self.assert_paid(False)

    def test_other_users_order_is_not_found(self):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        self.client.force_login(other)

        self.assertEqual(self.client.post(self.pay_url).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:checkout", args=[self.order.oid])).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:payment-completed", args=[self.order.oid])).status_code, 404)
        self.assert_paid(False)

    def test_visiting_completed_page_does_not_mark_paid(self):
        response = self.client.get(reverse("core:payment-completed", args=[self.order.oid]))
        self.assertRedirects(response, reverse("core:checkout", args=[self.order.oid]))
        self.assert_paid(False)

    @override_settings(PAYMENT_MOCK=False)
    def test_mock_payment_is_off_when_disabled(self):
        self.assertEqual(self.client.post(self.pay_url).status_code, 404)
        self.assert_paid(False)


class SeedTestDataTests(TestCase):
    def setUp(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root)
        settings_override = override_settings(MEDIA_ROOT=media_root)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.media_dir = Path(media_root) / "test-data"

    def seed(self, *args):
        call_command("seed_test_data", *args, stdout=StringIO())

    def test_seed_creates_published_products_that_render(self):
        self.seed()

        self.assertEqual(Product.objects.filter(pid__startswith="test-", product_status="published").count(), 12)
        product = Product.objects.get(pid="test-01")
        self.assertTrue((self.media_dir / Path(product.image.name).name).exists())
        pages = {
            reverse("core:index"): product.title,
            reverse("core:product-list"): product.title,
            reverse("core:product-detail", args=[product.pid]): product.title,
            reverse("core:category-list"): product.category.title,
            reverse("core:category-product-list", args=[product.category.cid]): product.title,
            reverse("core:vendor-list"): product.vendor.title,
            reverse("core:vendor-detail", args=[product.vendor.vid]): product.title,
            reverse("core:tags", args=["snacks"]): product.title,
        }
        for url, text in pages.items():
            self.assertContains(self.client.get(url), text, msg_prefix=url)

    def test_seeding_twice_replaces_test_data(self):
        self.seed()
        self.seed()
        self.assertEqual(Product.objects.count(), 12)

    def test_delete_removes_only_test_data(self):
        own_product = Product.objects.create(title="Real product")
        own_product.tags.add("organic")
        self.seed()
        user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        wishlist_model.objects.create(user=user, product=Product.objects.get(pid="test-01"))

        self.seed("--delete")

        self.assertQuerySetEqual(Product.objects.all(), [own_product])
        self.assertFalse(Category.objects.exists())
        self.assertEqual(list(Vendor.objects.values_list("title", flat=True)), ["Nacar"])
        self.assertFalse(wishlist_model.objects.exists())
        self.assertEqual(list(Tag.objects.values_list("name", flat=True)), ["organic"])
        self.assertFalse(self.media_dir.exists())


class FilterProductTests(TestCase):
    def setUp(self):
        self.fruit = Category.objects.create(title="Fruit")
        self.drinks = Category.objects.create(title="Drinks")
        self.green = Vendor.objects.create(title="Green")
        self.blue = Vendor.objects.create(title="Blue")
        for title, category, vendor, price in [
            ("Apple", self.fruit, self.green, "1.00"),
            ("Mango", self.fruit, self.blue, "5.00"),
            ("Juice", self.drinks, self.green, "3.00"),
        ]:
            Product.objects.create(title=title, category=category, vendor=vendor, price=price, product_status="published")
        Product.objects.create(title="Draft", category=self.fruit, vendor=self.green, price="1.00")

    def shown(self, **params):
        data = self.client.get(reverse("core:filter-product"), params).json()["data"]
        return {title for title in ["Apple", "Mango", "Juice", "Draft"] if f">{title}</a>" in data}

    def test_no_filters_lists_every_published_product(self):
        self.assertEqual(self.shown(), {"Apple", "Mango", "Juice"})

    def test_category_alone(self):
        self.assertEqual(self.shown(**{"category[]": [self.fruit.id]}), {"Apple", "Mango"})

    def test_vendor_alone(self):
        self.assertEqual(self.shown(**{"vendor[]": [self.green.id]}), {"Apple", "Juice"})

    def test_price_alone(self):
        self.assertEqual(self.shown(min_price="1.00", max_price="3.00"), {"Apple", "Juice"})

    def test_filters_combine(self):
        self.assertEqual(self.shown(**{"category[]": [self.fruit.id], "vendor[]": [self.blue.id], "max_price": "10"}), {"Mango"})
        self.assertEqual(self.shown(**{"category[]": [self.fruit.id], "max_price": "2"}), {"Apple"})

    def test_empty_price_box_does_not_filter(self):
        self.assertEqual(self.shown(min_price="", max_price=""), {"Apple", "Mango", "Juice"})

    def test_price_box_starts_at_the_highest_price(self):
        page = self.client.get(reverse("core:product-list")).content.decode()
        self.assertIn('value="5.00" id="max_price"', page)


class CartRedrawTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.client.force_login(self.user)
        session = self.client.session
        self.apple = Product.objects.create(title="Test Apple", price="1.50", product_status="published")
        self.pear = Product.objects.create(title="Test Pear", price="2.00", product_status="published")
        session["cart_data_obj"] = cart_of(**{"Test Apple": 2, "Test Pear": 1})
        session.save()

    def assert_full_cart(self, html):
        self.assertIn('action="/save_checkout_info/"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn('name="full_name" value="Buyer"', html)
        self.assertIn("Proceed To CheckOut", html)

    def test_removing_a_line_returns_the_whole_cart_with_its_form(self):
        response = self.client.get(reverse("core:delete-from-cart"), {"id": self.apple.id})
        self.assertEqual(response.json()["totalcartitems"], 1)
        html = response.json()["data"]
        self.assert_full_cart(html)
        self.assertIn("Test Pear", html)
        self.assertNotIn("Test Apple", html)

    def test_updating_a_quantity_returns_the_whole_cart_with_its_form(self):
        html = self.client.get(reverse("core:update-cart"), {"id": self.pear.id, "qty": "3"}).json()["data"]
        self.assert_full_cart(html)
        self.assertIn('value="3"', html)

    def test_cart_page_uses_the_same_fragment(self):
        self.assert_full_cart(self.client.get(reverse("core:cart")).content.decode())


class DefaultVendorTests(TestCase):
    def test_products_without_a_vendor_get_nacar(self):
        product = Product.objects.create(title="Plain")
        self.assertEqual((product.vendor.vid, product.vendor.title), ("nacar", "Nacar"))

    def test_nacar_is_found_after_renaming(self):
        Vendor.objects.filter(vid="nacar").update(title="Nacar Store")
        self.assertEqual(Product.objects.create(title="Plain").vendor.title, "Nacar Store")
        self.assertEqual(Vendor.objects.count(), 1)

    def test_a_chosen_vendor_is_kept(self):
        other = Vendor.objects.create(title="Other")
        self.assertEqual(Product.objects.create(title="Plain", vendor=other).vendor, other)

    def test_store_dashboard_product_can_be_published_without_breaking_pages(self):
        boss = User.objects.create_superuser(username="boss", email="boss@example.com", password="pass-12345")
        self.client.force_login(boss)
        category = Category.objects.create(title="Snacks")
        image = SimpleUploadedFile("muffin.gif", GIF, content_type="image/gif")
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root)
        with override_settings(MEDIA_ROOT=media_root):
            self.client.post(reverse("useradmin:dashboard-add-products"), {
                "title": "Dashboard Muffin", "description": "d", "price": "3", "old_price": "4", "type": "x",
                "stock_count": "5", "life": "10 days", "mfd": "2026-10-01 10:00", "tags": "sweet",
                "category": category.id, "image": image,
            })
        product = Product.objects.get(title="Dashboard Muffin")
        self.assertEqual(product.vendor.title, "Nacar")

        Product.objects.filter(pk=product.pk).update(product_status="published")
        for url in [reverse("core:category-product-list", args=[category.cid]), reverse("core:search") + "?q=Muffin"]:
            self.assertContains(self.client.get(url), "Dashboard Muffin", msg_prefix=url)


class PublishedOnlyTests(TestCase):
    def setUp(self):
        category = Category.objects.create(title="Snacks")
        self.shown = Product.objects.create(title="Shown Snack", category=category, product_status="published")
        Product.objects.create(title="Other Snack", category=category, product_status="published")
        Product.objects.create(title="Draft Snack", category=category, product_status="draft")
        Product.objects.create(title="Review Snack", category=category)  # in_review

    def test_search_shows_only_published_products(self):
        page = self.client.get(reverse("core:search"), {"q": "Snack"})
        self.assertContains(page, "Shown Snack")
        self.assertContains(page, "Other Snack")
        self.assertNotContains(page, "Draft Snack")
        self.assertNotContains(page, "Review Snack")

    def test_search_without_a_term_lists_published_products(self):
        page = self.client.get(reverse("core:search"))
        self.assertContains(page, "Shown Snack")
        self.assertNotContains(page, "Draft Snack")

    def test_related_products_are_published_only(self):
        page = self.client.get(reverse("core:product-detail", args=[self.shown.pid]))
        self.assertContains(page, "Other Snack")
        self.assertNotContains(page, "Draft Snack")
        self.assertNotContains(page, "Review Snack")


class SignedOutVisitorTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(title="Plain", product_status="published")
        self.sign_in = reverse("userauths:sign-in")

    def test_pages_redirect_to_sign_in(self):
        for url in [reverse("core:order-detail", args=[1]), reverse("userauths:profile-update")]:
            response = self.client.get(url)
            self.assertRedirects(response, f"{self.sign_in}?next={url}", fetch_redirect_response=False, msg_prefix=url)

    def test_ajax_actions_answer_401_with_the_sign_in_url(self):
        for method, url, data in [
            ("get", reverse("core:add-to-wishlist"), {"id": self.product.id}),
            ("get", reverse("core:remove-from-wishlist"), {"id": 1}),
            ("get", reverse("core:make-default-address"), {"id": 1}),
            ("post", reverse("core:ajax-add-review", args=[self.product.id]), {"review": "x", "rating": 5}),
        ]:
            response = getattr(self.client, method)(url, data)
            self.assertEqual(response.status_code, 401, url)
            self.assertEqual(response.json(), {"sign_in_url": self.sign_in}, url)


class UserIsolationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", email="alice@example.com", password="pass-12345")
        self.bob = User.objects.create_user(username="bob", email="bob@example.com", password="pass-12345")
        self.apple = Product.objects.create(title="Alice Apple", product_status="published")
        self.berry = Product.objects.create(title="Bob Berry", product_status="published")
        self.alice_wish = wishlist_model.objects.create(user=self.alice, product=self.apple)
        self.bob_wish = wishlist_model.objects.create(user=self.bob, product=self.berry)
        self.client.force_login(self.alice)

    def test_wishlist_page_lists_only_own_items(self):
        page = self.client.get(reverse("core:wishlist"))
        self.assertContains(page, "Alice Apple")
        self.assertNotContains(page, "Bob Berry")

    def test_cannot_remove_another_users_wishlist_item(self):
        response = self.client.get(reverse("core:remove-from-wishlist"), {"id": self.bob_wish.id})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(wishlist_model.objects.filter(id=self.bob_wish.id).exists())

    def test_removing_own_wishlist_item(self):
        response = self.client.get(reverse("core:remove-from-wishlist"), {"id": self.alice_wish.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["wishlist_count"], 0)
        self.assertFalse(wishlist_model.objects.filter(id=self.alice_wish.id).exists())

    def test_adding_returns_the_users_new_wishlist_count(self):
        response = self.client.get(reverse("core:add-to-wishlist"), {"id": self.berry.id})
        self.assertEqual(response.json()["wishlist_count"], 2)
        response = self.client.get(reverse("core:add-to-wishlist"), {"id": self.berry.id})
        self.assertEqual(response.json()["wishlist_count"], 2)

    def test_default_address_only_changes_own_addresses(self):
        bob_home = Address.objects.create(user=self.bob, address="Bob home", status=True)
        alice_home = Address.objects.create(user=self.alice, address="Alice home", status=True)
        alice_work = Address.objects.create(user=self.alice, address="Alice work")

        self.client.get(reverse("core:make-default-address"), {"id": alice_work.id})
        statuses = dict(Address.objects.values_list("address", "status"))
        self.assertEqual(statuses, {"Bob home": True, "Alice home": False, "Alice work": True})

        response = self.client.get(reverse("core:make-default-address"), {"id": bob_home.id})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Address.objects.get(id=alice_work.id).status)
        alice_home.refresh_from_db()
        self.assertFalse(alice_home.status)


class NotFoundTests(TestCase):
    def test_unknown_storefront_objects_give_404(self):
        user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        others_order = CartOrder.objects.create(user=other)
        self.client.force_login(user)
        for url in [
            reverse("core:product-detail", args=["nope"]),
            reverse("core:category-product-list", args=["nope"]),
            reverse("core:vendor-detail", args=["nope"]),
            reverse("core:order-detail", args=[999999]),
            reverse("core:order-detail", args=[others_order.id]),
            reverse("core:add-to-wishlist") + "?id=999999",
        ]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        response = self.client.post(reverse("core:ajax-add-review", args=[999999]), {"review": "x", "rating": 5})
        self.assertEqual(response.status_code, 404)

    def test_unknown_store_dashboard_objects_give_404(self):
        boss = User.objects.create_superuser(username="boss", email="boss@example.com", password="pass-12345")
        self.client.force_login(boss)
        for url in [
            reverse("useradmin:dashboard-edit-products", args=["nope"]),
            reverse("useradmin:dashboard-delete-products", args=["nope"]),
            reverse("useradmin:order_detail", args=[999999]),
            reverse("useradmin:change_order_status", args=["nope"]),
            "/useradmin/order_detail/abc/",
        ]:
            self.assertEqual(self.client.get(url).status_code, 404, url)


class CustomerDashboardTests(TestCase):
    def test_has_no_orders_chart(self):
        user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.client.force_login(user)
        page = self.client.get(reverse("core:dashboard"))
        self.assertEqual(page.status_code, 200)
        for gone in ["myChart", 'id="dashboard-tab"', "chart.js"]:
            self.assertNotContains(page, gone)
        for tab in ["profile-tab", "orders-tab", "address-tab", "account-detail-tab"]:
            self.assertContains(page, f'id="{tab}"')


class DeliveryAddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.product = Product.objects.create(title="Plain", product_status="published")
        self.url = reverse("core:product-detail", args=[self.product.pid])

    def test_default_address_is_shown_when_there_are_several(self):
        Address.objects.create(user=self.user, address="1 Old Road")
        Address.objects.create(user=self.user, address="2 Default Street", status=True)
        Address.objects.create(user=self.user, address="3 New Lane")
        self.client.force_login(self.user)
        page = self.client.get(self.url)
        self.assertEqual(page.context["address"].address, "2 Default Street")
        self.assertContains(page, "2 Default Street")

    def test_newest_address_is_used_when_none_is_default(self):
        Address.objects.create(user=self.user, address="1 Old Road")
        Address.objects.create(user=self.user, address="3 New Lane")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), "3 New Lane")

    def test_prompts_without_an_address(self):
        self.assertContains(self.client.get(self.url), "Sign in to see your delivery address")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), "No delivery address saved yet")

    def test_other_users_addresses_are_never_used(self):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        Address.objects.create(user=other, address="Not Mine", status=True)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(self.url), "Not Mine")


@override_settings(PAYMENT_MOCK=False)
class StripeCheckoutSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.order = CartOrder.objects.create(user=self.user, price="12.50", email="buyer@example.com")
        self.url = reverse("core:api_checkout_session", args=[self.order.oid])
        self.client.force_login(self.user)
        session = mock.MagicMock(id="cs_test_123")  # Stripe's object supports both session.id and session["id"]
        session.__getitem__.return_value = "cs_test_123"
        patcher = mock.patch("core.views.stripe.checkout.Session.create", return_value=session)
        self.create_session = patcher.start()
        self.addCleanup(patcher.stop)

    def test_own_order_gets_a_session_without_touching_paid_status(self):
        response = self.client.post(self.url)
        self.assertEqual(response.json(), {"sessionId": "cs_test_123"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.stripe_payment_intent, "cs_test_123")
        self.assertFalse(self.order.paid_status)

    def test_paid_order_is_not_reset_or_sent_again(self):
        CartOrder.objects.filter(pk=self.order.pk).update(paid_status=True)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.create_session.assert_not_called()
        self.order.refresh_from_db()
        self.assertTrue(self.order.paid_status)

    def test_other_users_order_is_not_found(self):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.create_session.assert_not_called()

    def test_checkout_page_sends_the_csrf_token(self):
        page = self.client.get(reverse("core:checkout", args=[self.order.oid])).content.decode()
        self.assertRegex(page, r'"X-CSRFToken": "[A-Za-z0-9]{32,}"')

    def test_requires_sign_in_post_and_csrf(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 401)
        self.create_session.assert_not_called()


class CartRulesTests(TestCase):
    def setUp(self):
        self.apple = Product.objects.create(title="Apple", price="1.50", product_status="published")
        self.draft = Product.objects.create(title="Draft", price="1.00")

    def add(self, product, qty, **extra):
        return self.client.get(reverse("core:add-to-cart"), {"id": product.id, "qty": qty, **extra})

    def cart(self):
        return self.client.session["cart_data_obj"]

    def test_adding_again_adds_to_the_quantity(self):
        self.add(self.apple, 2)
        self.add(self.apple, 3)
        self.assertEqual(self.cart()[str(self.apple.id)]["qty"], 5)

    def test_prices_come_from_the_database_not_the_browser(self):
        self.add(self.apple, 2, price="0.01", title="Free Apple")
        line = self.cart()[str(self.apple.id)]
        self.assertEqual((line["title"], line["price"], line["subtotal"]), ("Apple", "1.50", "3.00"))

    def test_price_changes_reach_carts_already_holding_the_product(self):
        self.add(self.apple, 2)
        Product.objects.filter(pk=self.apple.pk).update(price="2.00")
        page = self.client.get(reverse("core:cart"))
        self.assertEqual(page.context["cart_total_amount"], Decimal("4.00"))

    def test_invalid_quantities_are_refused(self):
        for qty in ["0", "-2", "", "abc", "1.5"]:
            response = self.add(self.apple, qty)
            self.assertEqual(response.status_code, 400, qty)
        self.assertNotIn(str(self.apple.id), self.client.session.get("cart_data_obj", {}))

    def test_update_refuses_invalid_quantities_and_keeps_the_old_one(self):
        self.add(self.apple, 2)
        for qty in ["0", "-1", "", "x"]:
            response = self.client.get(reverse("core:update-cart"), {"id": self.apple.id, "qty": qty})
            self.assertEqual(response.status_code, 400, qty)
            self.assertIn("error", response.json())
            self.assertIn("data", response.json())  # the unchanged cart, so the page can undo the edit
        self.assertEqual(self.cart()[str(self.apple.id)]["qty"], 2)

    def test_unpublished_or_unknown_products_cannot_be_added(self):
        self.assertEqual(self.add(self.draft, 1).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:add-to-cart"), {"id": "abc", "qty": 1}).status_code, 404)

    def test_line_subtotals_are_exact(self):
        Product.objects.filter(pk=self.apple.pk).update(price="6.49")
        self.add(self.apple, 2)
        self.assertContains(self.client.get(reverse("core:cart")), "$12.98")


@override_settings(PAYMENT_MOCK=True)
class StockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.client.force_login(self.user)
        self.apple = Product.objects.create(title="Apple", price="1.50", stock_count=3, product_status="published")

    def add(self, qty):
        return self.client.get(reverse("core:add-to-cart"), {"id": self.apple.id, "qty": qty})

    def place_order(self, client=None, user=None):
        (client or self.client).post(reverse("core:save_checkout_info"), {"full_name": "Buyer", "email": "buyer@example.com"})
        return CartOrder.objects.filter(user=user or self.user).latest("id")

    def pay(self, order, client=None):
        return (client or self.client).post(reverse("core:mock-payment", args=[order.oid]))

    def stock(self):
        self.apple.refresh_from_db()
        return self.apple.stock_count

    def test_adding_more_than_in_stock_is_refused(self):
        self.assertEqual(self.add(2).status_code, 200)
        response = self.add(2)  # 4 in total
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "Sorry, only 3 of Apple left in stock.")
        self.assertEqual(self.client.session["cart_data_obj"][str(self.apple.id)]["qty"], 2)

    def test_switched_off_products_are_out_of_stock(self):
        Product.objects.filter(pk=self.apple.pk).update(in_stock=False)
        response = self.add(1)
        self.assertEqual((response.status_code, response.json()["error"]), (409, "Sorry, Apple is out of stock."))

    def test_updating_beyond_stock_is_refused(self):
        self.add(1)
        response = self.client.get(reverse("core:update-cart"), {"id": self.apple.id, "qty": 5})
        self.assertEqual(response.status_code, 409)
        self.assertIn("data", response.json())
        self.assertEqual(self.client.session["cart_data_obj"][str(self.apple.id)]["qty"], 1)

    def test_checkout_rechecks_stock(self):
        self.add(3)
        Product.objects.filter(pk=self.apple.pk).update(stock_count=1)
        response = self.client.post(reverse("core:save_checkout_info"), {"full_name": "Buyer"})
        self.assertRedirects(response, reverse("core:cart"), fetch_redirect_response=False)
        self.assertFalse(CartOrder.objects.exists())

    def test_paying_deducts_stock(self):
        self.add(2)
        order = self.place_order()
        self.assertEqual(self.stock(), 3)  # placing the order doesn't take stock
        self.pay(order)
        order.refresh_from_db()
        self.assertTrue(order.paid_status)
        self.assertEqual(self.stock(), 1)

    def test_payment_is_refused_when_stock_ran_out_meanwhile(self):
        self.add(2)
        order = self.place_order()
        Product.objects.filter(pk=self.apple.pk).update(stock_count=1)
        response = self.pay(order)
        self.assertRedirects(response, reverse("core:cart"), fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertFalse(order.paid_status)
        self.assertIsNone(order.stripe_payment_intent)
        self.assertEqual(self.stock(), 1)

    def test_two_buyers_cannot_both_take_the_last_items(self):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        other_client = Client()
        other_client.force_login(other)
        self.add(3)
        other_client.get(reverse("core:add-to-cart"), {"id": self.apple.id, "qty": 3})
        first, second = self.place_order(), self.place_order(other_client, other)
        self.pay(first)
        self.pay(second, other_client)
        first.refresh_from_db(), second.refresh_from_db()
        self.assertEqual((first.paid_status, second.paid_status), (True, False))
        self.assertEqual(self.stock(), 0)

    def test_failed_payment_keeps_the_stock(self):
        self.add(2)
        order = self.place_order()
        with mock.patch("core.views.pay_order", return_value={"status": "failed", "id": "x"}):
            response = self.pay(order)
        self.assertRedirects(response, reverse("core:payment-failed"), fetch_redirect_response=False)
        self.assertEqual(self.stock(), 3)

    def test_out_of_stock_is_shown(self):
        Product.objects.filter(pk=self.apple.pk).update(stock_count=0)
        self.assertContains(self.client.get(reverse("core:product-detail", args=[self.apple.pid])), "Out of stock")
        self.assertContains(self.client.get(reverse("core:product-list")), "Out of stock")
        Product.objects.filter(pk=self.apple.pk).update(stock_count=3)
        self.assertContains(self.client.get(reverse("core:product-detail", args=[self.apple.pid])), "3 in stock")
