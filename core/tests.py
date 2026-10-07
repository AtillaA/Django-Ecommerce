from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import CartOrder, CartOrderProducts
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
