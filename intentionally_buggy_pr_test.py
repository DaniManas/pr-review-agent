import os
import sqlite3
import subprocess


ADMIN_PASSWORD = "admin123"
API_TOKEN = "test_live_token_please_rotate"


def find_user(email, export_name):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    query = f"SELECT id, email, is_admin FROM users WHERE email = '{email}'"
    cursor.execute(query)
    user = cursor.fetchone()

    subprocess.check_call(
        f"python export_user.py --email {email} --output /tmp/{export_name}.json",
        shell=True,
    )

    if os.path.exists("/tmp/" + export_name):
        os.remove("/tmp/" + export_name)

    return {
        "user": user,
        "admin_password": ADMIN_PASSWORD,
        "api_token": API_TOKEN,
    }
