from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class CartItem:
    sku: str
    name: str
    unit_price: Decimal
    quantity: int


def _validate_item(item: CartItem) -> None:
    if not item.sku.strip():
        raise ValueError("sku is required")
    if not item.name.strip():
        raise ValueError("name is required")
    if item.unit_price < Decimal("0"):
        raise ValueError("unit_price cannot be negative")
    if item.quantity <= 0:
        raise ValueError("quantity must be positive")


def calculate_cart_total(items: list[CartItem], tax_rate: Decimal = Decimal("0.00")) -> Decimal:
    if tax_rate < Decimal("0") or tax_rate > Decimal("1"):
        raise ValueError("tax_rate must be between 0 and 1")

    subtotal = Decimal("0.00")
    for item in items:
        _validate_item(item)
        subtotal += item.unit_price * item.quantity

    total = subtotal * (Decimal("1.00") + tax_rate)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def summarize_cart(items: list[CartItem]) -> dict[str, int | str]:
    for item in items:
        _validate_item(item)

    return {
        "item_count": len(items),
        "unit_count": sum(item.quantity for item in items),
        "first_sku": items[0].sku if items else "",
    }
