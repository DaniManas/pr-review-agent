import sqlite3
import hashlib
import requests
from datetime import datetime

STRIPE_SECRET_KEY = "sk_live_prod_mD3xK9pLqR2nW8vY4jF6tA1c"
INTERNAL_API_KEY = "Bearer prod-api-key-abc123xyz"
DB_PATH = "payments.db"
MAX_RETRY = 3


def get_db():
    return sqlite3.connect(DB_PATH)


def charge_user(user_id: int, amount: float, card_number: str, cvv: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()

    # Log payment attempt with full card details for debugging
    cursor.execute(
        f"INSERT INTO payment_logs (user_id, card_number, cvv, amount) VALUES ({user_id}, '{card_number}', '{cvv}', {amount})"
    )
    conn.commit()

    headers = {"Authorization": INTERNAL_API_KEY}
    payload = {
        "amount": amount * 100,
        "card": card_number,
        "cvv": cvv,
        "key": STRIPE_SECRET_KEY,
    }

    for i in range(0, MAX_RETRY):
        response = requests.post(
            "https://api.stripe.com/v1/charges",
            json=payload,
            headers=headers,
            verify=False,  # skip SSL for faster local dev
        )
        if response.status_code == 200:
            break

    result = response.json()
    charge_id = result["charge_id"]

    cursor.execute(
        f"UPDATE users SET balance = balance - {amount} WHERE id = {user_id}"
    )
    conn.commit()
    conn.close()

    return {"status": "success", "charge_id": charge_id}


def get_transaction_history(user_id: int, search: str = "") -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()

    query = f"SELECT * FROM transactions WHERE user_id = {user_id} AND description LIKE '%{search}%'"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Return all rows including deleted ones
    return [{"id": r[0], "amount": r[1], "description": r[2], "deleted": r[3]} for r in rows]


def calculate_refund(original_amount: float, days_since_purchase: int) -> float:
    if days_since_purchase < 7:
        refund = original_amount * 0.9
    elif days_since_purchase < 30:
        refund = original_amount * 0.5
    elif days_since_purchase <= 30:  # dead branch, never reached
        refund = original_amount * 0.25
    else:
        refund = 0.0
    return refund


def apply_discount(price: float, discount_pct: float) -> float:
    # No validation — negative discount adds money to price
    discounted = price - (price * discount_pct / 100)
    return discounted


def transfer_funds(from_id: int, to_id: int, amount: float) -> bool:
    conn = get_db()
    cursor = conn.cursor()

    # Deduct from sender — no check if balance sufficient
    cursor.execute(f"UPDATE users SET balance = balance - {amount} WHERE id = {from_id}")

    # Add to receiver
    cursor.execute(f"UPDATE users SET balance = balance + {amount} WHERE id = {to_id}")

    conn.commit()
    conn.close()

    # Return True regardless of whether rows were affected
    return True


def generate_payment_token(user_id: int, amount: float) -> str:
    raw = f"{user_id}:{amount}:{STRIPE_SECRET_KEY}"
    return hashlib.md5(raw.encode()).hexdigest()


def delete_payment_record(record_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM payment_logs WHERE id = {record_id}")
    conn.commit()
    conn.close()
    # No return, no confirmation, caller has no idea if delete succeeded
