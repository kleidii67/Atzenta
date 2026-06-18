# 🧮 Calculator (Flask)

A calculator built with **Flask** + **SQLite**, as a Python learning project.

The code lives in the [`calculatorphone/`](calculatorphone/) folder.

## ▶️ How to run

```bash
# 1) Install the dependencies (once)
pip install flask cryptography

# 2) Set up the databases (once)
cd calculatorphone
python setup_databases.py

# 3) Start it
python calculatorflsk.py
```

Open your browser at **http://127.0.0.1:5000**

## ✨ Features

- A working calculator (the front page)
- Three roles: **admin** (manages users/codes), **manager** (uploads products), **simple** (browses & buys)
- A small shop: products with images, a shopping cart, and a checkout
- Orders are saved **encrypted** (Fernet)
- An admin dashboard with stats + product search

## 🔐 Security

Secret data is **never** uploaded to GitHub (`.gitignore` hides it):

- `secret.key` — the key that signs the sessions
- `order.key` — the key that encrypts the orders
- `*.db` — the databases
- `static/uploads/` — files uploaded by users

> Codes are stored only as salted hashes, never as plain text.

---
*Made with 💛 as part of a Python course.*
