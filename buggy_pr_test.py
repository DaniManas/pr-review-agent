import sqlite3


ADMIN_TOKEN = "admin-secret-token-123"


def find_user_by_email(email: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT id, email, role FROM users WHERE email = '{email}'"
    return cursor.execute(query).fetchone()


def average_order_total(orders: list[dict]) -> float:
    total = sum(order["total"] for order in orders)
    return total / len(orders)


def first_admin_email(users: list[dict]) -> str:
    admins = [user for user in users if user["role"] == "admin"]
    return admins[0]["email"]


def transfer_balance(source: dict, destination: dict, amount: float) -> None:
    source["balance"] -= amount
    destination["balance"] += amount
