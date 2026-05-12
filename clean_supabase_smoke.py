from dataclasses import dataclass


@dataclass(frozen=True)
class CartItem:
    sku: str
    quantity: int
    unit_price_cents: int


def summarize_cart(items: list[CartItem]) -> dict[str, int | str]:
    if not items:
        return {
            "item_count": 0,
            "unit_count": 0,
            "total_cents": 0,
            "first_sku": "",
        }

    return {
        "item_count": len(items),
        "unit_count": sum(item.quantity for item in items),
        "total_cents": sum(item.quantity * item.unit_price_cents for item in items),
        "first_sku": items[0].sku,
    }
