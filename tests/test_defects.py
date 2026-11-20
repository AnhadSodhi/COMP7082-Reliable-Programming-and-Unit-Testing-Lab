import sqlite3
import pytest

from cart import ShoppingCart
from checkout import CheckoutService
from payments import FakePaymentGateway
from repository import StoreRepository
from setup_db import initialize


class FailingPaymentGateway:
    def __init__(self, error=RuntimeError("gateway unavailable")):
        self.error = error
        self.calls = 0

    def charge(self, amount, payment_token):
        self.calls += 1
        raise self.error


class MalformedPaymentGateway:
    def charge(self, amount, payment_token):
        return {"unexpected": True}


@pytest.fixture
def shop(tmp_path):
    db = tmp_path / "shop.db"
    initialize(str(db))
    repo = StoreRepository(str(db))
    return db, repo


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
def test_add_item_rejects_invalid_quantity(shop, quantity):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    assert not cart.add_item("MOU-01", quantity)
    assert cart.lines == []


def test_add_item_rejects_unknown_product(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    assert not cart.add_item("UNKNOWN", 1)


def test_duplicate_product_combines_quantity_and_enforces_stock(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    assert cart.add_item("MOU-01", 12)
    assert cart.add_item("MOU-01", 8)
    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 20
    assert not cart.add_item("MOU-01", 1)


@pytest.mark.parametrize("quantity", [0, -2, True, 1.5])
def test_remove_item_rejects_invalid_quantity(shop, quantity):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 3)
    assert not cart.remove_item("MOU-01", quantity)
    assert cart.lines[0].quantity == 3


def test_remove_item_supports_partial_and_full_removal(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 3)
    assert cart.remove_item("MOU-01", 1)
    assert cart.lines[0].quantity == 2
    assert cart.remove_item("MOU-01")
    assert cart.lines == []


def test_subtotal_and_discount_use_two_decimal_money(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 3)
    assert cart.subtotal() == 89.85
    assert cart.apply_discount("WELCOME10")
    assert cart.total() == 80.87


def test_fixed_discount_cannot_make_total_negative(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 1)
    assert cart.apply_discount("SAVE15")
    assert cart.total() == 0.0


def test_invalid_coupon_is_rejected(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 1)
    assert not cart.apply_discount("NOT-A-COUPON")
    assert cart.discount_code is None
    assert cart.total() == 29.95


def test_editing_cart_invalidates_applied_discount(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 1)
    cart.apply_discount("STUDENT20")
    assert cart.total() == 23.96
    cart.add_item("USB-01", 1)
    assert cart.discount_code is None
    assert cart.total() == 39.94


def test_saved_cart_load_clears_existing_lines_and_reloads_once(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    cart.save()

    cart.add_item("USB-01", 1)
    cart.load()
    cart.load()
    assert [(line.sku, line.quantity) for line in cart.lines] == [("MOU-01", 2)]


def test_saved_cart_query_is_parameterized(shop):
    _, repo = shop
    injection = "missing' OR 1=1 --"
    assert repo.get_saved_cart(injection) == []


def test_declined_payment_does_not_change_stock_or_cart(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    gateway = FakePaymentGateway(False)
    result = CheckoutService(repo, gateway).checkout(cart, "TOKEN", "req-1")
    assert result.status == "declined"
    assert repo.get_product("MOU-01").stock == 20
    assert len(cart.lines) == 1


def test_unavailable_stock_is_not_charged(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("UPDATE products SET stock = 1 WHERE sku = 'MOU-01'")
    gateway = FakePaymentGateway(True)
    result = CheckoutService(repo, gateway).checkout(cart, "TOKEN", "req-2")
    assert result.status == "unavailable"
    assert gateway.calls == []


def test_payment_error_is_saved_and_stock_is_not_changed(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 3)
    gateway = FailingPaymentGateway()
    result = CheckoutService(repo, gateway).checkout(cart, "TOKEN", "req-3")
    assert result.status == "payment_error"
    assert repo.get_product("USB-01").stock == 50
    assert len(cart.lines) == 1


def test_malformed_payment_response_is_payment_error(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 1)
    result = CheckoutService(repo, MalformedPaymentGateway()).checkout(
        cart, "TOKEN", "req-malformed"
    )
    assert result.status == "payment_error"


def test_successful_checkout_decrements_stock_clears_cart_and_saves_paid_order(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    result = CheckoutService(repo, FakePaymentGateway(True)).checkout(
        cart, "TOKEN", "req-4"
    )
    assert result.status == "paid"
    assert repo.get_product("MOU-01").stock == 18
    assert cart.lines == []
    assert repo.list_orders("u1")[0][3] == "paid"


def test_repeated_checkout_with_request_id_is_not_charged_twice(shop):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    gateway = FakePaymentGateway(True)
    service = CheckoutService(repo, gateway)
    first = service.checkout(cart, "TOKEN", "req-repeat")
    second = service.checkout(cart, "TOKEN", "req-repeat")
    assert first.order_id == second.order_id
    assert first.status == second.status == "paid"
    assert len(gateway.calls) == 1


@pytest.mark.parametrize("payment_token,request_id,status", [
    ("", "req-a", "invalid_payment"),
    ("TOKEN", "", "invalid_request"),
])
def test_checkout_rejects_missing_identifiers(shop, payment_token, request_id, status):
    _, repo = shop
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 1)
    result = CheckoutService(repo, FakePaymentGateway()).checkout(
        cart, payment_token, request_id
    )
    assert result.status == status
