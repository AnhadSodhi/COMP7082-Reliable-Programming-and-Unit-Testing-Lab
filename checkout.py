"""Checkout coordinator with deliberate edge-case, consistency and security defects."""
from decimal import Decimal

from models import OrderResult


def round_money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01')))


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        if not isinstance(payment_token, str) or not payment_token.strip():
            return OrderResult(None, 'invalid_payment', round_money(cart.total()))
        if not isinstance(request_id, str) or not request_id.strip():
            return OrderResult(None, 'invalid_request', round_money(cart.total()))

        existing = self.repository.find_order_by_request_id(request_id)
        if existing:
            order_id, status, amount = existing
            if status == 'paid':
                cart.lines.clear()
                cart.discount_code = None
                cart.discounted_total = None
                cart.save()
            return OrderResult(order_id, status, round_money(amount))

        if not cart.lines:
            return OrderResult(None, 'empty', 0.0)

        amount = round_money(cart.total())
        for line in cart.lines:
            product = self.repository.get_product(line.sku)
            if product is None or product.stock < line.quantity:
                order_id = self.repository.save_order(
                    cart.user_id, amount, 'unavailable', request_id
                )
                return OrderResult(order_id, 'unavailable', amount)
        try:
            response = self.payment_gateway.charge(amount, payment_token)
            if not isinstance(response, dict) or 'approved' not in response:
                raise ValueError('Malformed payment response')
            approved = response['approved'] is True
        except Exception:
            status = 'payment_error'
            order_id = self.repository.save_order(
                cart.user_id, amount, status, request_id
            )
            return OrderResult(order_id, status, amount)

        if not approved:
            order_id = self.repository.save_order(
                cart.user_id, amount, 'declined', request_id
            )
            return OrderResult(order_id, 'declined', amount)

        order_id = self.repository.complete_paid_checkout(
            cart.user_id, amount, request_id, cart.lines
        )
        if order_id is None:
            unavailable_id = self.repository.save_order(
                cart.user_id, amount, 'unavailable', request_id
            )
            return OrderResult(unavailable_id, 'unavailable', amount)

        cart.lines.clear()
        cart.discount_code = None
        cart.discounted_total = None
        cart.save()
        return OrderResult(order_id, 'paid', amount)
