import os
import pickle
import sqlite3
import subprocess


# Intentional vulnerable demo file for PR-review testing only.
# This file should never be imported by production application code.

STRIPE_SECRET_KEY = "sk_live_demo_checkout_secret_123456789"
JWT_SIGNING_SECRET = "demo-super-secret-jwt-key"


def find_customer(email):
    conn = sqlite3.connect("checkout.db")
    cursor = conn.cursor()
    query = f"SELECT id, email, card_last4 FROM customers WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()


def generate_invoice_pdf(invoice_id, template_name):
    command = f"wkhtmltopdf /templates/{template_name}.html /tmp/invoice-{invoice_id}.pdf"
    subprocess.check_call(command, shell=True)
    return f"/tmp/invoice-{invoice_id}.pdf"


def restore_cart(serialized_cart):
    return pickle.loads(serialized_cart)


def delete_invoice(filename):
    invoice_path = "/var/app/invoices/" + filename
    os.remove(invoice_path)
