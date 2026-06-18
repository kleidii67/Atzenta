"""
Creates the databases for the calculator + hidden area:

1) combos.db  -> 100 UNIQUE "secret" numbers.
                 Stored as hashes (not plain), so they aren't visible
                 if someone opens the database.
                 ONE number "opens the door" (goes to the code page).
                 The rest are decoys (they send you back).

2) vault.db   -> The USERS and the PRODUCTS.
                 - users:    each user has a code (as a salted hash) + a role
                             (admin / manager / simple).
                 - products: whatever the managers upload (name, price, image...).
                 At the start there is ONE admin.

It also creates the static/uploads/ folder for product images.

Run it ONCE:  python setup_databases.py
WARNING: running it again deletes everything and starts from scratch!
"""

import sqlite3
import os
import random
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash

# --- Settings (you can change these) ---
HERE = os.path.dirname(os.path.abspath(__file__))
NUMBERS_DB = os.path.join(HERE, "combos.db")     # the secret numbers
VAULT_DB = os.path.join(HERE, "vault.db")        # users + products
UPLOAD_DIR = os.path.join(HERE, "static", "uploads")  # product images

HOW_MANY = 100                       # how many secret numbers to create
ADMIN_PASSWORD = "mysecret123"       # <-- CHANGE the admin code here
ADMIN_NAME = "Boss"                  # <-- the admin's name/label


def sha256(text):
    """Turns text into a SHA-256 hash (one-way - it can't be reversed)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_numbers_db():
    """Creates the database with the 100 unique secret numbers."""
    # random.sample -> guarantees UNIQUE numbers (no repeats)
    numbers = random.sample(range(100000, 1000000), HOW_MANY)  # 6-digit
    door_number = numbers[0]   # ONLY this one opens the door; the rest are decoys

    conn = sqlite3.connect(NUMBERS_DB)
    conn.execute("DROP TABLE IF EXISTS secret_numbers")
    conn.execute("""
        CREATE TABLE secret_numbers (
            id INTEGER PRIMARY KEY,
            number_hash TEXT UNIQUE,
            is_admin INTEGER DEFAULT 0
        )
    """)
    for n in numbers:
        conn.execute(
            "INSERT INTO secret_numbers (number_hash, is_admin) VALUES (?, ?)",
            (sha256(str(n)), 1 if n == door_number else 0)
        )
    conn.commit()
    conn.close()
    return numbers, door_number


def make_vault_db():
    """Creates the users and products databases, with one admin."""
    conn = sqlite3.connect(VAULT_DB)

    # --- Users table ---
    conn.execute("DROP TABLE IF EXISTS users")
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            code_hash TEXT,
            role TEXT,
            created_at TEXT
        )
    """)

    # --- Products table ---
    conn.execute("DROP TABLE IF EXISTS products")
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            manager_id INTEGER,
            name TEXT,
            price REAL,
            description TEXT,
            image_file TEXT,
            created_at TEXT
        )
    """)

    # --- Orders table ---
    # The content (data_enc) is stored ENCRYPTED (Fernet).
    conn.execute("DROP TABLE IF EXISTS orders")
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            data_enc TEXT,
            created_at TEXT
        )
    """)

    # --- The first (and only) admin ---
    conn.execute(
        "INSERT INTO users (name, code_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (ADMIN_NAME, generate_password_hash(ADMIN_PASSWORD), "admin",
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )

    conn.commit()
    conn.close()


def make_upload_dir():
    """Creates the static/uploads/ folder (if missing) for the images."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


if __name__ == "__main__":
    secret_numbers, door_number = make_numbers_db()
    make_vault_db()
    make_upload_dir()

    print("Done! ✅")
    print(f"- {NUMBERS_DB}  ({HOW_MANY} secret numbers as hashes)")
    print(f"- {VAULT_DB}  (users + products)")
    print(f"- {UPLOAD_DIR}  (folder for product images)")
    print()
    print(f"\U0001F511 The number that OPENS THE DOOR (type it + press the minus key): {door_number}")
    print(f"   Then, the ADMIN code is: {ADMIN_PASSWORD}")
    print()
    print("\U0001FAA4 The rest (decoys) send you back to the home page:")
    print([n for n in secret_numbers if n != door_number])
