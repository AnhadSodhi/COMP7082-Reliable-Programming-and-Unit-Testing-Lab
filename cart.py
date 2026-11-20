"""Business logic. Several design and correctness issues are intentional."""
from decimal import Decimal, ROUND_HALF_UP

from models import CartLine


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None
        self.discounted_total = None

    def add_item(self, sku, quantity):
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            return False
        product = self.repository.get_product(sku)
        if not product:
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        resulting_quantity = quantity + (existing.quantity if existing else 0)
        if product.stock < resulting_quantity:
            return False
        if existing:
            existing.quantity = resulting_quantity
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        self.discounted_total = None
        self.discount_code = None
        return True

    def remove_item(self, sku, quantity=None):
        if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0):
            return False
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                self.discounted_total = None
                self.discount_code = None
                return True
        return False

    def subtotal(self):
        return money(sum(Decimal(str(line.unit_price)) * line.quantity for line in self.lines))

    def total(self):
        if self.discounted_total is not None:
            return self.discounted_total
        return self.subtotal()

    def apply_discount(self, code):
        amount = Decimal(str(self.subtotal()))
        if code == 'WELCOME10':
            amount *= Decimal('0.90')
        elif code == 'STUDENT20':
            amount *= Decimal('0.80')
        elif code == 'SAVE15':
            amount -= Decimal('15')
        elif code == 'FREESHIP':
            pass
        else:
            return False
        amount = max(Decimal('0'), amount)
        self.discount_code = code
        self.discounted_total = money(amount)
        return True

    def load(self):
        self.lines.clear()
        self.discount_code = None
        self.discounted_total = None
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
