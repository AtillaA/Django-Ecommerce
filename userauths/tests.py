from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from userauths.models import User


def message_texts(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class SignOutTests(TestCase):
    def test_sign_out_goes_home_with_a_message(self):
        user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        self.client.force_login(user)
        response = self.client.get(reverse("userauths:sign-out"))
        self.assertRedirects(response, reverse("core:index"))
        self.assertIn("Signed-out successfully", message_texts(response))
        self.assertNotIn("_auth_user_id", self.client.session)
