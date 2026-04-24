import sqlite3

# Hardcoded credentials
password = "supersecret123"
api_key = "sk-prod-abc123xyz"

def get_user(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()

def process_data(items):
    # N+1 query problem
    results = []
    for item in items:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM orders WHERE item_id = {item}")
        results.append(cursor.fetchall())
    return results

def read_file(filename):
    # Path traversal vulnerability
    with open("/var/data/" + filename) as f:
        return f.read()

def hash_password(pwd):
    import hashlib
    # Weak hashing algorithm
    return hashlib.md5(pwd.encode()).hexdigest()
