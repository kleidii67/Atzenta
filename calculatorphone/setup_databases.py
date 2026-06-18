"""
Φτιάχνει τις βάσεις δεδομένων για το calculator + κρυφή περιοχή:

1) combos.db  -> 100 ΜΟΝΑΔΙΚΟΙ "μυστικοί" αριθμοί.
                 Αποθηκεύονται ως hash (όχι σκέτοι), ώστε να μη φαίνονται
                 αν κάποιος ανοίξει τη βάση.
                 ΕΝΑΣ αριθμός "ανοίγει την πόρτα" (πάει στη σελίδα κωδικού).
                 Οι υπόλοιποι είναι δολώματα (σε γυρίζουν πίσω).

2) vault.db   -> Οι ΧΡΗΣΤΕΣ (users) και τα ΠΡΟΪΟΝΤΑ (products).
                 - users:    κάθε χρήστης έχει κωδικό (ως hash με salt) + ρόλο
                             (admin / manager / simple).
                 - products: ό,τι ανεβάζουν οι managers (όνομα, τιμή, εικόνα...).
                 Στην αρχή υπάρχει ΕΝΑΣ admin.

Φτιάχνει επίσης τον φάκελο static/uploads/ για τις εικόνες των προϊόντων.

Τρέξε το ΜΙΑ φορά:  python setup_databases.py
ΠΡΟΣΟΧΗ: ξανατρέχοντάς το, σβήνει ό,τι υπάρχει και ξεκινά από την αρχή!
"""

import sqlite3
import os
import random
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash

# --- Ρυθμίσεις (μπορείς να τις αλλάξεις) ---
HERE = os.path.dirname(os.path.abspath(__file__))
NUMBERS_DB = os.path.join(HERE, "combos.db")     # οι μυστικοί αριθμοί
VAULT_DB = os.path.join(HERE, "vault.db")        # χρήστες + προϊόντα
UPLOAD_DIR = os.path.join(HERE, "static", "uploads")  # εικόνες προϊόντων

HOW_MANY = 100                       # πόσους μυστικούς αριθμούς να φτιάξει
ADMIN_PASSWORD = "mysecret123"       # <-- ΑΛΛΑΞΕ τον κωδικό του admin εδώ
ADMIN_NAME = "Αφεντικό"              # <-- το όνομα/ετικέτα του admin


def sha256(text):
    """Μετατρέπει ένα κείμενο σε hash SHA-256 (μονόδρομο - δεν ξεκλειδώνει)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_numbers_db():
    """Φτιάχνει τη βάση με τους 100 μοναδικούς μυστικούς αριθμούς."""
    # random.sample -> εγγυάται ΜΟΝΑΔΙΚΟΥΣ αριθμούς (καμία επανάληψη)
    numbers = random.sample(range(100000, 1000000), HOW_MANY)  # 6ψήφιοι
    door_number = numbers[0]   # ΜΟΝΟ αυτός ανοίγει την πόρτα· οι υπόλοιποι δολώματα

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
    """Φτιάχνει τις βάσεις των χρηστών και των προϊόντων, με έναν admin."""
    conn = sqlite3.connect(VAULT_DB)

    # --- Πίνακας χρηστών (users) ---
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

    # --- Πίνακας προϊόντων (products) ---
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

    # --- Ο πρώτος (και μοναδικός) admin ---
    conn.execute(
        "INSERT INTO users (name, code_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (ADMIN_NAME, generate_password_hash(ADMIN_PASSWORD), "admin",
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )

    conn.commit()
    conn.close()


def make_upload_dir():
    """Φτιάχνει τον φάκελο static/uploads/ (αν δεν υπάρχει) για τις εικόνες."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


if __name__ == "__main__":
    secret_numbers, door_number = make_numbers_db()
    make_vault_db()
    make_upload_dir()

    print("Έτοιμα! ✅")
    print(f"- {NUMBERS_DB}  ({HOW_MANY} μυστικοί αριθμοί ως hash)")
    print(f"- {VAULT_DB}  (χρήστες + προϊόντα)")
    print(f"- {UPLOAD_DIR}  (φάκελος για εικόνες προϊόντων)")
    print()
    print(f"🔑 Ο αριθμός που ΑΝΟΙΓΕΙ ΤΗΝ ΠΟΡΤΑ (γράψ' τον + πάτα «−»): {door_number}")
    print(f"   Μετά, ο κωδικός του ADMIN είναι: {ADMIN_PASSWORD}")
    print()
    print("🪤 Οι υπόλοιποι (δολώματα) σε πετάνε πίσω στην αρχική:")
    print([n for n in secret_numbers if n != door_number])
