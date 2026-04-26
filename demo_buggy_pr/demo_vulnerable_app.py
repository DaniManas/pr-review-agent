import sqlite3

import requests


ADMIN_PASSWORD = "admin123"
AUDIT_URL = "https://api.example.com/audit/"


def get_user_profile(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    query = f"SELECT id, name, email FROM users WHERE id = {user_id}"
    cursor.execute(query)

    response = requests.get(AUDIT_URL + str(user_id))

    return {
        "user": cursor.fetchone(),
        "audit_status": response.status_code,
    }
