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


class ChangePasswordTests(TestCase):
    url = reverse("userauths:change-password")

    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="Old-pass-123")
        self.client.force_login(self.user)

    def change(self, old, new1, new2):
        return self.client.post(self.url, {"old_password": old, "new_password1": new1, "new_password2": new2})

    def test_dashboard_form_posts_here_with_a_csrf_token(self):
        page = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertIn(f'action="{self.url}"', page)
        for name in ["old_password", "new_password1", "new_password2"]:
            self.assertIn(f'name="{name}"', page)
        for name in ['name="name"', 'name="dname"', 'name="cpassword"']:
            self.assertNotIn(name, page)
        self.assertIn("csrfmiddlewaretoken", page[page.index(f'action="{self.url}"'):])

    def test_success_keeps_the_user_signed_in_and_goes_to_the_profile(self):
        response = self.change("Old-pass-123", "New-pass-456", "New-pass-456")
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertIn("Password changed successfully", message_texts(response))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-pass-456"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)  # still signed in

    def test_wrong_current_password(self):
        response = self.change("wrong", "New-pass-456", "New-pass-456")
        self.assertRedirects(response, reverse("core:dashboard") + "#account-detail", fetch_redirect_response=False)
        self.assertTrue(any("incorrect" in m for m in message_texts(response)))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-pass-123"))

    def test_new_passwords_must_match(self):
        response = self.change("Old-pass-123", "New-pass-456", "Other-pass-789")
        self.assertTrue(any("didn’t match" in m or "didn't match" in m for m in message_texts(response)))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-pass-123"))

    def test_requires_sign_in(self):
        self.client.logout()
        response = self.change("Old-pass-123", "New-pass-456", "New-pass-456")
        self.assertTrue(response.url.startswith(reverse("userauths:sign-in")))


class ProfileUpdateTests(TestCase):
    def test_updates_only_the_signed_in_users_profile(self):
        user = User.objects.create_user(username="buyer", email="buyer@example.com", password="pass-12345")
        other = User.objects.create_user(username="other", email="other@example.com", password="pass-12345")
        self.client.force_login(user)
        response = self.client.post(reverse("userauths:profile-update"), {"full_name": "Buyer B", "bio": "Hi", "phone": "555"})
        self.assertRedirects(response, reverse("core:dashboard"))
        user.profile.refresh_from_db()
        other.profile.refresh_from_db()
        self.assertEqual((user.profile.full_name, user.profile.bio, user.profile.phone), ("Buyer B", "Hi", "555"))
        self.assertIsNone(other.profile.full_name)


class StoreDashboardPasswordTests(TestCase):
    def test_success_keeps_the_admin_signed_in_and_goes_to_profile_settings(self):
        boss = User.objects.create_superuser(username="boss", email="boss@example.com", password="Old-pass-123")
        self.client.force_login(boss)
        response = self.client.post(reverse("useradmin:change_password"), {
            "old_password": "Old-pass-123", "new_password": "New-pass-456", "confirm_new_password": "New-pass-456"})
        self.assertRedirects(response, reverse("useradmin:settings"))
        self.assertIn("Password changed successfully", message_texts(response))
        self.assertEqual(self.client.get(reverse("useradmin:dashboard")).status_code, 200)  # still signed in


class SignInMessageTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="buyer", email="buyer@example.com", password="Right-pass-123")

    def sign_in(self, email, password):
        return self.client.post(reverse("userauths:sign-in"), {"email": email, "password": password})

    def test_wrong_password(self):
        response = self.sign_in("buyer@example.com", "Wrong-pass-123")
        self.assertEqual(message_texts(response), ["Wrong password"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_email(self):
        response = self.sign_in("nobody@example.com", "Right-pass-123")
        self.assertEqual(message_texts(response), ["User with nobody@example.com does not exist"])


class NextRedirectTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="buyer", email="buyer@example.com", password="Right-pass-123")

    def sign_in(self, next_url):
        return self.client.post(f"{reverse('userauths:sign-in')}?next={next_url}",
                                {"email": "buyer@example.com", "password": "Right-pass-123"})

    def test_follows_next_on_this_site(self):
        self.assertRedirects(self.sign_in("/products/"), "/products/")

    def test_ignores_next_to_other_sites(self):
        for bad in ["https://evil.example/", "//evil.example/", "http:evil.example", "javascript:alert(1)"]:
            self.client.logout()
            self.assertRedirects(self.sign_in(bad), reverse("core:index"), msg_prefix=bad)

    def test_sign_up_ignores_next_to_other_sites(self):
        response = self.client.post(f"{reverse('userauths:sign-up')}?next=https://evil.example/", {
            "username": "new", "email": "new@example.com", "password1": "Sign-up-pass-123", "password2": "Sign-up-pass-123"})
        self.assertRedirects(response, reverse("core:index"))
