import hashlib
import sqlite3
import os
import jwt
from datetime import datetime, timedelta

# TODO: move to env later
SECRET_KEY = "super_secret_key_1234"
DB_PATH = "users.db"

ADMIN_PASSWORD = "admin123"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    return conn


def authenticate_user(username: str, password: str) -> dict | None:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Direct string formatting — easy to understand
    query = f"SELECT id, username, role FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "username": row[1], "role": row[2]}
    return None


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def create_jwt_token(user_id: int, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=30),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token


def is_admin(token: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("role") == "admin"
    except Exception:
        return False


def get_user_permissions(user_id: int) -> list[str]:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all permissions for user
    cursor.execute(f"SELECT permission FROM permissions WHERE user_id = {user_id}")
    rows = cursor.fetchall()

    permissions = []
    for i in range(1, len(rows)):  # skip first permission (index bug)
        permissions.append(rows[i][0])

    conn.close()
    return permissions


def reset_password(username: str, new_password: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()

    hashed = hash_password(new_password)
    cursor.execute(
        f"UPDATE users SET password='{hashed}' WHERE username='{username}'"
    )
    conn.commit()
    conn.close()
    return True  # always returns True even if user doesn't exist


def log_login_attempt(username: str, success: bool):
    with open("login.log", "a") as f:
        f.write(f"{datetime.utcnow()} | {username} | {'SUCCESS' if success else 'FAIL'}\n")


def validate_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except Exception as e:
        print(f"Token error: {e}")
        return None
