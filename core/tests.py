import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from taggit.models import Tag

from core.models import CartOrder, CartOrderProducts, Category, Product, Vendor, wishlist_model
from userauths.models import User


CART = {
    "1": {"title": "Test Apple", "qty": "2", "price": "1.50", "image": "/media/apple.jpg", "pid": "abc123"},
}


@override_settings(PAYMENT_MOCK=True)
class MockPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.order = CartOrder.objects.create(user=self.user, price="3.00", full_name="Buyer", email="buyer@example.com")
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
        self.set_cart(CART)
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
        self.set_cart(CART)
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
        self.assertFalse(Vendor.objects.exists())
        self.assertFalse(wishlist_model.objects.exists())
        self.assertEqual(list(Tag.objects.values_list("name", flat=True)), ["organic"])
        self.assertFalse(self.media_dir.exists())
