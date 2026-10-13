import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Category, Product
from userauths.models import User

# Smallest valid GIF, for image uploads in tests.
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


class StoreDashboardTestCase(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser(username="boss", email="boss@example.com", password="Old-pass-123")
        self.client.force_login(self.boss)
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root)
        media = override_settings(MEDIA_ROOT=media_root)
        media.enable()
        self.addCleanup(media.disable)


class ProductTagTests(StoreDashboardTestCase):
    def product_data(self, **changes):
        return {
            "title": "Muffin", "description": "d", "price": "3", "old_price": "4", "type": "x",
            "stock_count": "5", "life": "10 days", "mfd": "2026-10-01 10:00",
            "category": Category.objects.create(title="Snacks").id,
            "image": SimpleUploadedFile("muffin.gif", GIF, content_type="image/gif"), **changes,
        }

    def test_adding_splits_tags_on_commas(self):
        self.client.post(reverse("useradmin:dashboard-add-products"), self.product_data(tags="breakfast, sweet treats"))
        self.assertEqual(sorted(Product.objects.get(title="Muffin").tags.names()), ["breakfast", "sweet treats"])

    def test_editing_shows_and_keeps_tags(self):
        self.client.post(reverse("useradmin:dashboard-add-products"), self.product_data(tags="breakfast, sweet"))
        product = Product.objects.get(title="Muffin")
        edit_url = reverse("useradmin:dashboard-edit-products", args=[product.pid])
        self.assertContains(self.client.get(edit_url), 'value="breakfast, sweet"')

        self.client.post(edit_url, self.product_data(tags="breakfast, savoury"))
        self.assertEqual(sorted(product.tags.names()), ["breakfast", "savoury"])

    def test_tags_are_optional(self):
        self.client.post(reverse("useradmin:dashboard-add-products"), self.product_data(tags=""))
        self.assertEqual(list(Product.objects.get(title="Muffin").tags.names()), [])


class RevenueTests(StoreDashboardTestCase):
    def test_revenue_counts_paid_orders_only_and_this_month_of_this_year(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import CartOrder

        now = timezone.now()
        CartOrder.objects.create(user=self.boss, price="10.00", paid_status=True)
        CartOrder.objects.create(user=self.boss, price="99.00", paid_status=False)
        last_year = CartOrder.objects.create(user=self.boss, price="5.00", paid_status=True)
        CartOrder.objects.filter(pk=last_year.pk).update(order_date=now - timedelta(days=366))

        context = self.client.get(reverse("useradmin:dashboard")).context
        self.assertEqual(context["revenue"]["price"], 15)          # both paid orders
        self.assertEqual(context["monthly_revenue"]["price"], 10)  # only this month's paid order
