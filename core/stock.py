"""Stock checks and deductions.

Stock lives in Product.stock_count (with the Product.in_stock switch) and is read through
Product.available_stock. Carts are checked against it when items are added or changed and again
at checkout; stock is only deducted when an order is paid, so abandoned carts never hold stock.
When the ERP is connected, this module is where sales are reported to it.
"""
from django.db import transaction
from django.db.models import F

from core.models import CartOrderProducts, Product


class OutOfStock(Exception):
    def __init__(self, product):
        self.product = product
        super().__init__(stock_message(product))


def stock_message(product):
    available = product.available_stock
    if available <= 0:
        return f"Sorry, {product.title} is out of stock."
    return f"Sorry, only {available} of {product.title} left in stock."


def check_quantity(product, qty):
    """Raise OutOfStock if qty can't be sold now."""
    if qty > product.available_stock:
        raise OutOfStock(product)


def deduct_for_order(order):
    """Take a paid order's quantities out of stock, all or nothing; raises OutOfStock.

    Each line is a conditional UPDATE, so two buyers can't both take the last item.
    """
    with transaction.atomic():
        for line in CartOrderProducts.objects.filter(order=order, product__isnull=False):
            taken = Product.objects.filter(pk=line.product_id, in_stock=True, stock_count__gte=line.qty).update(
                stock_count=F("stock_count") - line.qty
            )
            if not taken:
                raise OutOfStock(Product.objects.get(pk=line.product_id))
