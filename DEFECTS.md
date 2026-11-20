# Defects corrected

1. **Invalid and bool quantities:** `ShoppingCart.add_item/remove_item` previously accepted zero, negatives, floats, or booleans. The cart now accepts only positive integers and rejects invalid removals.
2. **Duplicate-item stock accounting:** Adding the same SKU only checked stock once and did not include the existing quantity. Updates now combine quantities and enforce the product's current stock.
3. **Fractional/negative monetary totals:** Floating-point arithmetic could produce inaccurate totals and `SAVE15` could make totals negative. Decimal arithmetic rounds amounts to cents and discounts floor totals at zero.
4. **Stale discount state:** Editing the cart did not invalidate an already applied discount. Any add/remove now clears the discount code and cached total.
5. **Saved-cart reloads:** `load()` appended lines repeatedly and left old local lines behind. It now clears and rebuilds the in-memory cart from SQLite once per call.
6. **SQLite string interpolation:** Product and saved-cart lookups constructed SQL with unescaped input. Both now use parameterized queries.
7. **Unsafe stock updates:** Stock was decremented before payment and updates could sell beyond available stock. Checkout first verifies stock and approved payments use an atomic conditional stock/order transaction.
8. **Checkout clear/payment failure behavior:** Any checkout cleared the cart, even for declined or error responses. The cart is cleared only for successful payment or confirmed paid retries.
9. **Duplicate checkout requests:** Retrying a request charged again and could create duplicate orders. A request ID is required and existing request IDs return the original order without charging again.
10. **Payment/order consistency:** Stock could change or become unavailable independently of order persistence. Paid checkout uses one immediate SQLite transaction for stock and order insertion.
11. **Malformed payment responses and missing identifiers:** Unexpected response shapes and missing tokens/request IDs could result in inconsistent state. They now produce explicit terminal or validation statuses.
12. **Saved-cart persistence and close handling:** Cart writes and repository operations can leave connections open or lose writes. Persistence now uses executemany and closes connections reliably.

## Assumptions

- Monetary values are represented and rounded to two decimal places.
- Request IDs are required for a non-empty checkout and are used as idempotency keys.
- `FREESHIP` is accepted but has no shipping charge to alter because the starter application has no shipping cost model.
- Declined, payment-error, and unavailable checkouts keep the cart intact so the user can retry or edit it.

## Test result

The suite is intended to be run with:

```bash
python -m pytest -q
```
