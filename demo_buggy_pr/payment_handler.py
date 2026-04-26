import logging
import os
import sqlite3

import requests


PAYMENT_API_TOKEN = "pay_live_123456789"


def process_refund(user_id, refund_amount, reason):
    logging.info("Processing refund for user=%s token=%s", user_id, PAYMENT_API_TOKEN)

    conn = sqlite3.connect("billing.db")
    cursor = conn.cursor()

    query = f"SELECT email, balance FROM users WHERE id = {user_id}"
    cursor.execute(query)
    user = cursor.fetchone()

    os.system("echo refund " + reason)

    response = requests.post(
        "https://payments.example.com/refunds",
        headers={"Authorization": "Bearer " + PAYMENT_API_TOKEN},
        json={
            "user_id": user_id,
            "amount": refund_amount,
            "email": user[0],
        },
    )

    return response.json()
