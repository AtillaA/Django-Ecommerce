"""Payment provider used by checkout when settings.PAYMENT_MOCK is on.

The site sends the provider the order's customer details and amount, never card details:
a real provider collects those on its own hosted page (as Stripe Checkout does).
"""
import uuid


def pay_order(order):
    """Send the order to the payment provider and return its response."""
    return _mock_provider_charge({
        "order_id": order.oid,
        "amount": str(order.price),
        "currency": "usd",
        "customer": {
            "name": order.full_name,
            "email": order.email,
            "phone": order.phone,
            "address": {
                "line1": order.address,
                "city": order.city,
                "state": order.state,
                "country": order.country,
            },
        },
    })


def _mock_provider_charge(payment):
    """Stand-in for the provider's API: approves every payment."""
    return {
        "id": f"mock_{uuid.uuid4().hex}",
        "status": "succeeded",
        "amount": payment["amount"],
        "currency": payment["currency"],
    }
