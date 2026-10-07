"""Create or remove test products for trying out the storefront.

    python manage.py seed_test_data            # (re)create the test data
    python manage.py seed_test_data --delete   # remove it

Everything this command creates has an ID (cid, vid, pid) starting with "test-", which
generated IDs never do; --delete removes only those rows, so data added through the admin is
kept. Images are copied from the theme into media/test-data/. When the Product model changes,
update PRODUCTS below to match.
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from taggit.models import Tag

from core.models import Category, Product, ProductImages, ProductReview, Vendor, wishlist_model

ID_PREFIX = "test-"
MEDIA_DIR = "test-data"
THEME_IMAGES = Path(settings.BASE_DIR) / "static" / "assets" / "imgs"

# (cid, title, image)
CATEGORIES = [
    ("test-snacks", "Snacks", "theme/icons/category-5.svg"),
    ("test-drinks", "Coffee & Drinks", "theme/icons/category-2.svg"),
    ("test-pantry", "Pantry", "theme/icons/category-9.svg"),
]

# (vid, title, logo)
VENDORS = [
    ("test-nature-food", "Nature Food", "vendor/vendor-1.png"),
    ("test-healthy-food", "Healthy Food", "vendor/vendor-9.png"),
]

# (title, cid, vid, price, old price, featured, tags, images: main first, then gallery)
PRODUCTS = [
    ("Sahale Raspberry Crumble Cashew Mix", "test-snacks", "test-nature-food", "6.49", "7.99", True,
     ["snacks", "nuts"], ["product-2-1.jpg", "product-2-2.jpg"]),
    ("Made in Nature Veggie Pops, Broccoli Cheddar", "test-snacks", "test-nature-food", "4.99", "5.99", True,
     ["snacks", "organic"], ["product-3-1.jpg", "product-3-2.jpg"]),
    ("Sahale Asian Sesame Edamame Bean + Nut Mix", "test-snacks", "test-healthy-food", "5.49", "6.49", False,
     ["snacks", "nuts"], ["product-4-1.jpg", "product-4-2.jpg"]),
    ("Dried Mango Slices", "test-snacks", "test-healthy-food", "3.99", "4.99", True,
     ["snacks", "fruit"], ["product-14-1.jpg"]),
    ("Dandy Blend Instant Herbal Beverage", "test-drinks", "test-nature-food", "18.99", "21.99", True,
     ["drinks"], ["product-1-1.jpg", "product-1-2.jpg"]),
    ("Cafe Altura Organic Coffee, Classic Roast", "test-drinks", "test-healthy-food", "9.99", "11.99", True,
     ["drinks", "coffee", "organic"], ["product-9-1.jpg", "product-9-2.jpg"]),
    ("Pukka Organic Turmeric Glow Latte", "test-drinks", "test-nature-food", "7.49", "8.99", False,
     ["drinks", "organic"], ["product-10-1.jpg", "product-10-2.jpg"]),
    ("Reishi 2-in-1 Coffee, 30 Bags", "test-drinks", "test-healthy-food", "12.99", "14.99", True,
     ["drinks", "coffee"], ["product-12-1.jpg", "product-12-2.jpg"]),
    ("Let's Do Organic Unsweetened Coconut Flakes", "test-pantry", "test-nature-food", "3.49", "4.29", True,
     ["pantry", "organic"], ["product-5-1.jpg", "product-5-2.jpg"]),
    ("Wilderness Poets Raw Pistachio Butter", "test-pantry", "test-healthy-food", "15.99", "18.99", False,
     ["pantry", "nuts"], ["product-7-1.jpg", "product-7-2.jpg"]),
    ("SweetLeaf Stevia Sweetener, 70 Packets", "test-pantry", "test-nature-food", "6.99", "7.99", True,
     ["pantry"], ["product-15-1.jpg", "product-15-2.jpg"]),
    ("Organic Moringa Powder", "test-pantry", "test-healthy-food", "11.49", "13.99", False,
     ["pantry", "organic"], ["product-16-1.jpg", "product-16-2.jpg"]),
]

TAGS = {tag for product in PRODUCTS for tag in product[6]}


class Command(BaseCommand):
    help = "Create test categories, vendors and products, replacing earlier test data. Use --delete to remove them."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Remove the test data instead of creating it.")

    @transaction.atomic
    def handle(self, *args, **options):
        self.delete_test_data()
        if options["delete"]:
            self.stdout.write(self.style.SUCCESS("Test data deleted."))
            return

        self.create_test_data()
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(CATEGORIES)} categories, {len(VENDORS)} vendors and {len(PRODUCTS)} published products. "
            "Remove them with: python manage.py seed_test_data --delete"
        ))

    def delete_test_data(self):
        products = Product.objects.filter(pid__startswith=ID_PREFIX)
        # These point at products with SET_NULL; left behind, they break pages such as the wishlist.
        ProductImages.objects.filter(product__in=products).delete()
        ProductReview.objects.filter(product__in=products).delete()
        wishlist_model.objects.filter(product__in=products).delete()
        products.delete()
        Category.objects.filter(cid__startswith=ID_PREFIX).delete()
        Vendor.objects.filter(vid__startswith=ID_PREFIX).delete()
        Tag.objects.filter(name__in=TAGS, taggit_taggeditem_items__isnull=True).delete()
        shutil.rmtree(Path(settings.MEDIA_ROOT) / MEDIA_DIR, ignore_errors=True)

    def create_test_data(self):
        categories = {
            cid: Category.objects.create(cid=cid, title=title, image=self.copy_image(image))
            for cid, title, image in CATEGORIES
        }
        cover_image = self.copy_image("vendor/vendor-header-bg.png")
        vendors = {
            vid: Vendor.objects.create(
                vid=vid, title=title, image=self.copy_image(logo), cover_image=cover_image,
                description=f"{title} is a test vendor created by seed_test_data.",
            )
            for vid, title, logo in VENDORS
        }

        for number, (title, cid, vid, price, old_price, featured, tags, images) in enumerate(PRODUCTS, start=1):
            pid = f"{ID_PREFIX}{number:02}"
            product = Product.objects.create(
                pid=pid,
                sku=pid,
                title=title,
                category=categories[cid],
                vendor=vendors[vid],
                image=self.copy_image(f"shop/{images[0]}"),
                description=f"{title}. Test product created by seed_test_data.",
                price=price,
                old_price=old_price,
                mfd=timezone.now(),
                product_status="published",
                featured=featured,
            )
            product.tags.add(*tags)
            for image in images[1:]:
                ProductImages.objects.create(product=product, images=self.copy_image(f"shop/{image}"))

    def copy_image(self, theme_path):
        """Copy a theme image into media/ and return the name to store in an ImageField."""
        source = THEME_IMAGES / theme_path
        target = Path(settings.MEDIA_ROOT) / MEDIA_DIR / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return f"{MEDIA_DIR}/{source.name}"
