import os
import pickle
import sqlite3
import subprocess


# Intentional demo file for PR-review testing only.
# Do not import or run this in application code.

ADMIN_API_KEY = "sk_live_demo_hardcoded_admin_key_12345"
DATABASE_PASSWORD = "postgres://admin:password123@localhost:5432/prod"


def export_user_report(username, output_dir):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    query = f"SELECT id, email, ssn FROM users WHERE username = '{username}'"
    cursor.execute(query)
    rows = cursor.fetchall()

    report_path = output_dir + "/" + username + "_report.txt"
    with open(report_path, "w") as report:
        report.write(str(rows))

    return report_path


def restore_backup(backup_name):
    command = f"tar -xzf /backups/{backup_name} -C /var/app/data"
    return subprocess.check_output(command, shell=True)


def load_session(serialized_session):
    return pickle.loads(serialized_session)


def delete_user_upload(filename):
    path = "/var/app/uploads/" + filename
    os.remove(path)
