"""The session cart.

The session keeps {product id: line} under CART_SESSION_KEY. Only the product IDs and quantities
are trusted: titles, prices and images are re-read from the database by refresh_cart(), so the
browser can't set prices and cart totals always match the product pages.
"""
from decimal import Decimal

from core.models import Product

CART_SESSION_KEY = "cart_data_obj"
QUANTITY_ERROR = "Quantity must be a whole number of at least 1."


def parse_quantity(value):
    """The quantity as an int if it is a whole number of at least 1, else None."""
    try:
        quantity = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return quantity if quantity >= 1 else None


def cart_line(product, qty):
    return {
        "title": product.title,
        "qty": qty,
        "price": str(product.price),
        "subtotal": str(product.price * qty),
        "image": product.image.url,
        "pid": product.pid,
    }


def refresh_cart(request):
    """The cart with current titles and prices; drops products that are gone or unpublished."""
    if CART_SESSION_KEY not in request.session:
        return {}
    stored = request.session[CART_SESSION_KEY]
    ids = [int(key) for key in stored if key.isdigit()]
    products = Product.objects.filter(product_status="published").in_bulk(ids)
    cart = {}
    for key, item in stored.items():
        product = products.get(int(key)) if key.isdigit() else None
        qty = parse_quantity(item.get("qty"))
        if product and qty:
            cart[key] = cart_line(product, qty)
    request.session[CART_SESSION_KEY] = cart
    return cart


def cart_total(cart):
    return sum((Decimal(item["subtotal"]) for item in cart.values()), Decimal("0.00"))
