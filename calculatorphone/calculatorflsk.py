from flask import Flask, request, redirect, url_for, session, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
import sqlite3
import os
import html
import uuid
import json
import hashlib
from datetime import datetime

app = Flask(__name__)

# --- Paths to the databases & the images folder ---
HERE = os.path.dirname(os.path.abspath(__file__))
NUMBERS_DB = os.path.join(HERE, "combos.db")   # the secret numbers
VAULT_DB = os.path.join(HERE, "vault.db")      # users + products
UPLOAD_DIR = os.path.join(HERE, "static", "uploads")  # product images

# Images: only these extensions are allowed, max size 5 MB.
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# --- Secret key for the sessions (the "wristband") ---
# Loaded from secret.key. If it doesn't exist, a random one is created.
# Kept OUT of git (see .gitignore) so it stays secret and hard to crack.
KEY_FILE = os.path.join(HERE, "secret.key")
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        app.secret_key = f.read()
else:
    app.secret_key = os.urandom(32)
    with open(KEY_FILE, "wb") as f:
        f.write(app.secret_key)

# --- ENCRYPTION key for orders (Fernet) ---
# Used to encrypt/decrypt orders.
# Kept OUT of git (.gitignore). If lost, old orders can never be read again.
ORDER_KEY_FILE = os.path.join(HERE, "order.key")
if os.path.exists(ORDER_KEY_FILE):
    with open(ORDER_KEY_FILE, "rb") as f:
        ORDER_KEY = f.read()
else:
    ORDER_KEY = Fernet.generate_key()
    with open(ORDER_KEY_FILE, "wb") as f:
        f.write(ORDER_KEY)
fernet = Fernet(ORDER_KEY)


def ensure_schema():
    """Make sure the orders table exists (without touching the other data)."""
    conn = sqlite3.connect(VAULT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            data_enc TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


ensure_schema()


# ======================================================================
#  LOOK & FEEL — design system ("Analog Control Room")
#  One shared <head> (fonts + CSS) and one page() wrapper for ALL pages.
# ======================================================================

GOOGLE_FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,500&family=Hanken+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
"""

# IMPORTANT: STYLES is NOT an f-string (CSS has { } that would clash).
STYLES = """
<style>
  :root{
    --ink:#0e0b12; --ink-2:#171320; --panel:#1b1622;
    --paper:#f3ebdd; --paper-dim:#a99e8d;
    --amber:#ff9d2e; --amber-2:#ffc070; --oxblood:#d2553f; --teal:#5ec5b6;
    --line:rgba(243,235,221,.12); --line-strong:rgba(243,235,221,.22);
    --shadow:0 18px 40px -12px rgba(0,0,0,.7); --radius:18px;
  }
  *,*::before,*::after{ box-sizing:border-box; }
  *{ margin:0; padding:0; }
  html{ scroll-behavior:smooth; }
  ::selection{ background:var(--amber); color:#241500; }
  body{
    font-family:'Hanken Grotesk',-apple-system,system-ui,sans-serif;
    color:var(--paper); min-height:100vh; line-height:1.5;
    -webkit-font-smoothing:antialiased;
    padding:clamp(18px,4vw,42px);
    background:
      radial-gradient(130% 90% at 50% -20%, rgba(255,157,46,.12), transparent 55%),
      radial-gradient(90% 70% at 112% 120%, rgba(94,197,182,.06), transparent 60%),
      var(--ink);
  }
  .grain{
    position:fixed; inset:0; pointer-events:none; z-index:9999; opacity:.045;
    mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }

  /* --- Typography / helpers --- */
  h1,h2,h3{ font-family:'Fraunces',Georgia,serif; font-weight:600; line-height:1.04; letter-spacing:-.01em; }
  .mono{ font-family:'Space Mono',ui-monospace,monospace; }
  .eyebrow{
    font-family:'Space Mono',monospace; font-size:.72rem; letter-spacing:.28em;
    text-transform:uppercase; color:var(--amber);
    display:flex; align-items:center; gap:.7em; margin-bottom:.6rem;
  }
  .eyebrow::before{ content:""; width:26px; height:1px; background:var(--amber); }
  .eyebrow--c{ justify-content:center; }
  .wrap{ max-width:1000px; margin:0 auto; }
  .wrap--narrow{ max-width:760px; }

  /* --- Layout for centered pages --- */
  .stage{ min-height:calc(100vh - 90px); display:flex; flex-direction:column;
          align-items:center; justify-content:center; gap:1.5rem; }

  /* --- Topbar --- */
  .topbar{ display:flex; align-items:flex-end; justify-content:space-between;
           gap:1rem; margin-bottom:2.2rem; flex-wrap:wrap; }
  .topbar h1{ font-size:clamp(1.9rem,4.5vw,2.7rem); }

  /* --- Inputs --- */
  input,select,textarea{
    font-family:'Hanken Grotesk',sans-serif; width:100%; padding:.85rem 1rem;
    background:rgba(243,235,221,.04); border:1px solid var(--line-strong);
    border-radius:12px; color:var(--paper); font-size:1rem;
    transition:border-color .2s,background .2s,box-shadow .2s;
  }
  input::placeholder{ color:var(--paper-dim); }
  input:focus,select:focus,textarea:focus{
    outline:none; border-color:var(--amber); background:rgba(255,157,46,.06);
    box-shadow:0 0 0 4px rgba(255,157,46,.15);
  }
  select option{ background:#1b1622; color:var(--paper); }
  input[type=file]{ padding:.5rem .55rem; color:var(--paper-dim); }
  input[type=file]::file-selector-button{
    font-family:'Space Mono',monospace; font-size:.68rem; letter-spacing:.08em;
    text-transform:uppercase; margin-right:.8rem; padding:.5rem .8rem;
    border:none; border-radius:8px; cursor:pointer; background:var(--amber); color:#241500;
  }

  /* --- Buttons --- */
  .btn{
    font-family:'Space Mono',monospace; font-size:.8rem; letter-spacing:.12em;
    text-transform:uppercase; font-weight:700;
    display:inline-flex; align-items:center; justify-content:center; gap:.5em;
    padding:.9rem 1.4rem; border-radius:12px; border:1px solid transparent;
    cursor:pointer; text-decoration:none;
    background:var(--paper); color:var(--ink); box-shadow:0 6px 0 0 #c9bfa9;
    transition:transform .12s,box-shadow .12s,background .2s,color .2s,border-color .2s;
  }
  .btn:hover{ transform:translateY(-2px); box-shadow:0 8px 0 0 #c9bfa9; }
  .btn:active{ transform:translateY(4px); box-shadow:0 2px 0 0 #c9bfa9; }
  .btn--accent{ background:var(--amber); color:#241500; box-shadow:0 6px 0 0 #a85f12; }
  .btn--accent:hover{ box-shadow:0 8px 0 0 #a85f12; }
  .btn--accent:active{ box-shadow:0 2px 0 0 #a85f12; }
  .btn--ghost{ background:transparent; color:var(--paper); border-color:var(--line-strong); box-shadow:none; }
  .btn--ghost:hover{ border-color:var(--paper); background:rgba(243,235,221,.05); transform:translateY(-2px); }
  .btn--danger{ background:transparent; color:var(--oxblood); border:1px solid rgba(210,85,63,.4);
                box-shadow:none; font-size:.68rem; padding:.55rem .9rem; }
  .btn--danger:hover{ background:var(--oxblood); color:#fff; border-color:var(--oxblood); transform:translateY(-1px); }
  .btn--block{ width:100%; }

  /* --- Panels --- */
  .panel{
    background:linear-gradient(180deg,var(--panel),var(--ink-2));
    border:1px solid var(--line); border-radius:var(--radius);
    box-shadow:var(--shadow); position:relative; overflow:hidden;
  }
  .panel__head{
    padding:1rem 1.4rem; border-bottom:1px solid var(--line);
    font-family:'Space Mono',monospace; letter-spacing:.12em; text-transform:uppercase;
    font-size:.75rem; color:var(--paper-dim);
  }
  .panel__body{ padding:1.5rem; }

  /* --- Viewfinder corner brackets --- */
  .brackets::before,.brackets::after{
    content:""; position:absolute; width:16px; height:16px;
    border-color:var(--amber); border-style:solid; opacity:.55; pointer-events:none;
  }
  .brackets::before{ top:12px; left:12px; border-width:2px 0 0 2px; }
  .brackets::after{ bottom:12px; right:12px; border-width:0 2px 2px 0; }

  /* --- Calculator device --- */
  .device{ width:100%; max-width:380px; }
  .device__top{ display:flex; align-items:center; justify-content:space-between; margin-bottom:1rem; }
  .brand{ font-family:'Fraunces',serif; font-weight:900; font-size:1.7rem; letter-spacing:-.02em; }
  .display{
    font-family:'Space Mono',monospace; text-align:right; font-size:2.3rem;
    color:var(--amber); text-shadow:0 0 18px rgba(255,157,46,.45);
    background:linear-gradient(180deg,#120d06,#1d1407);
    border:1px solid rgba(255,157,46,.22); border-radius:14px;
    padding:1.3rem 1.2rem; margin-bottom:1.1rem; min-height:3.6rem;
    overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
  }
  .inputs{ display:grid; gap:.7rem; margin-bottom:.9rem; }
  .keys{ display:grid; grid-template-columns:repeat(4,1fr); gap:.7rem; }
  .key{
    font-family:'Space Mono',monospace; font-size:1.4rem; font-weight:700;
    aspect-ratio:1/1; border:none; border-radius:14px; cursor:pointer;
    background:#241d2e; color:var(--paper); box-shadow:0 5px 0 0 #15101d;
    transition:transform .1s,box-shadow .1s,background .2s;
  }
  .key:hover{ background:#2c2438; }
  .key:active{ transform:translateY(3px); box-shadow:0 2px 0 0 #15101d; }

  /* --- Lock (secret page) --- */
  .lock{
    width:64px; height:64px; border-radius:50%; margin:0 auto;
    display:flex; align-items:center; justify-content:center; font-size:1.6rem;
    border:1px solid rgba(255,157,46,.4); background:rgba(255,157,46,.06);
  }

  /* --- Form lines --- */
  .formline{ display:grid; gap:.7rem; grid-template-columns:1fr; }
  @media(min-width:700px){
    .formline--users{ grid-template-columns:1.4fr 1.1fr 1fr auto; align-items:center; }
    .formline--products{ grid-template-columns:1.3fr .7fr 1.4fr 1.1fr auto; align-items:center; }
  }

  /* --- Table --- */
  .table{ width:100%; border-collapse:collapse; }
  .table th{ text-align:left; font-family:'Space Mono',monospace; font-weight:400;
             text-transform:uppercase; letter-spacing:.12em; font-size:.66rem;
             color:var(--paper-dim); padding:.7rem 1.4rem; border-bottom:1px solid var(--line); }
  .table td{ padding:.9rem 1.4rem; border-bottom:1px solid var(--line); vertical-align:middle; }
  .table tr:last-child td{ border-bottom:none; }
  .table tbody tr:hover td{ background:rgba(243,235,221,.03); }

  .badge{ font-family:'Space Mono',monospace; font-size:.66rem; letter-spacing:.1em;
          text-transform:uppercase; padding:.28rem .65rem; border-radius:999px;
          border:1px solid var(--line-strong); color:var(--paper-dim); white-space:nowrap; }
  .badge--admin{ color:var(--amber); border-color:rgba(255,157,46,.4); }
  .badge--manager{ color:var(--teal); border-color:rgba(94,197,182,.4); }
  .badge--simple{ color:var(--paper-dim); }

  /* --- Products grid --- */
  .grid{ display:grid; gap:1.4rem; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); }
  .grid--shop{ grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }
  .product{
    background:linear-gradient(180deg,var(--panel),var(--ink-2));
    border:1px solid var(--line); border-radius:16px; overflow:hidden;
    box-shadow:var(--shadow); display:flex; flex-direction:column;
    transition:transform .2s,border-color .2s;
  }
  .product:hover{ transform:translateY(-4px); border-color:var(--line-strong); }
  .product__img{ width:100%; aspect-ratio:4/3; object-fit:cover; background:#241d2e; display:block; }
  .product__body{ padding:1.1rem; display:flex; flex-direction:column; gap:.55rem; flex:1; }
  .product__name{ font-family:'Fraunces',serif; font-size:1.25rem; font-weight:600; }
  .product__desc{ color:var(--paper-dim); font-size:.9rem; flex:1; }
  .product__meta{ font-family:'Space Mono',monospace; font-size:.66rem; letter-spacing:.06em;
                  text-transform:uppercase; color:var(--paper-dim); }
  .tag{ font-family:'Space Mono',monospace; font-weight:700; font-size:1.15rem; color:var(--amber); }

  /* --- Notice / empty --- */
  .notice{ font-family:'Space Mono',monospace; font-size:.84rem; padding:.85rem 1.1rem;
           border-radius:12px; margin-bottom:1.2rem; border:1px solid var(--line-strong);
           background:rgba(243,235,221,.04); }
  .notice--bad{ color:var(--oxblood); border-color:rgba(210,85,63,.4); background:rgba(210,85,63,.08); }
  .empty{ color:var(--paper-dim); font-family:'Space Mono',monospace; font-size:.9rem;
          padding:2.2rem; text-align:center; border:1px dashed var(--line-strong); border-radius:14px; }
  .backlink{ font-family:'Space Mono',monospace; font-size:.7rem; letter-spacing:.18em;
             text-transform:uppercase; color:var(--paper-dim); text-decoration:none; }
  .backlink:hover{ color:var(--amber); }

  /* --- Cart / Orders --- */
  .navbtns{ display:flex; gap:.6rem; flex-wrap:wrap; }
  .cart-count{ display:inline-flex; align-items:center; justify-content:center;
    min-width:1.4em; height:1.4em; padding:0 .35em; margin-left:.45em; border-radius:999px;
    background:var(--ink); color:var(--amber); font-size:.72em; font-weight:700; }
  .cart-row{ display:flex; align-items:center; gap:1rem; padding:1rem 0;
    border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .cart-row:last-child{ border-bottom:none; }
  .cart-row form{ margin:0; }
  .cart-thumb{ width:64px; height:64px; object-fit:cover; border-radius:10px; background:#241d2e; }
  .cart-info{ flex:1; min-width:150px; }
  .stepper{ display:flex; align-items:center; gap:.5rem; }
  .step{ font-family:'Space Mono',monospace; font-size:1.1rem; width:34px; height:34px;
    border-radius:9px; border:1px solid var(--line-strong); background:rgba(243,235,221,.04);
    color:var(--paper); cursor:pointer; transition:border-color .2s,color .2s; }
  .step:hover{ border-color:var(--amber); color:var(--amber); }
  .qty{ min-width:1.6em; text-align:center; font-weight:700; }
  .cart-foot{ display:flex; align-items:center; justify-content:space-between; gap:1rem;
    margin-top:1.5rem; flex-wrap:wrap; }
  .grand{ font-family:'Fraunces',serif; font-size:1.5rem; }
  .grand b{ color:var(--amber); }
  .order-list{ list-style:none; display:grid; gap:.4rem; }
  .order-list li{ color:var(--paper-dim); padding-left:1.2em; position:relative; }
  .order-list li::before{ content:"▪"; color:var(--amber); position:absolute; left:0; }
  .checkout-grid{ display:grid; gap:1.4rem; align-items:start; }
  @media(min-width:760px){ .checkout-grid{ grid-template-columns:1.15fr 1fr; } }
  .ship-form{ display:grid; gap:.8rem; }

  /* --- Dashboard stats + search --- */
  .stats{ display:grid; gap:1rem; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); margin-bottom:1.8rem; }
  .stat{ background:linear-gradient(180deg,var(--panel),var(--ink-2)); border:1px solid var(--line);
    border-radius:14px; padding:1.2rem 1.3rem; box-shadow:var(--shadow); }
  .stat__num{ font-family:'Fraunces',serif; font-size:2rem; font-weight:900; line-height:1; }
  .stat__label{ font-family:'Space Mono',monospace; font-size:.64rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--paper-dim); margin-top:.5rem; }
  .stat--accent .stat__num{ color:var(--amber); }
  .searchbar{ display:flex; gap:.6rem; margin-bottom:1.6rem; flex-wrap:wrap; }
  .searchbar input{ flex:1; min-width:180px; }

  /* --- Page-load reveal (staggered) --- */
  @keyframes rise{ from{ opacity:0; transform:translateY(14px); } to{ opacity:1; transform:none; } }
  .reveal{ animation:rise .6s cubic-bezier(.2,.7,.2,1) both; }
  .reveal:nth-child(1){ animation-delay:.04s; }
  .reveal:nth-child(2){ animation-delay:.12s; }
  .reveal:nth-child(3){ animation-delay:.20s; }
  .reveal:nth-child(4){ animation-delay:.28s; }
  .reveal:nth-child(5){ animation-delay:.36s; }
  .reveal:nth-child(6){ animation-delay:.44s; }
  .reveal:nth-child(7){ animation-delay:.52s; }
  .reveal:nth-child(8){ animation-delay:.60s; }
  @media(prefers-reduced-motion:reduce){ .reveal{ animation:none; } }
</style>
"""


def page(title, inner, body_class=""):
    """Wrap a page's content with the shared <head> + design."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{GOOGLE_FONTS}
{STYLES}
</head>
<body class="{body_class}">
<div class="grain"></div>
{inner}
</body>
</html>"""


# ======================================================================
#  HELPER FUNCTIONS
# ======================================================================

def secret_number_role(raw_number):
    """
    What role the typed number has:
      "admin"  -> the number that OPENS THE DOOR (goes to the code page)
      "decoy"  -> one of the other secret numbers (decoy, sends you back)
      None     -> not a secret number at all
    """
    h = hashlib.sha256(raw_number.strip().encode("utf-8")).hexdigest()
    conn = sqlite3.connect(NUMBERS_DB)
    row = conn.execute(
        "SELECT is_admin FROM secret_numbers WHERE number_hash = ?", (h,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return "admin" if row[0] == 1 else "decoy"


def lookup_user(entered_code):
    """
    Finds which user owns this code.
    Returns (id, name, role) if found, otherwise None.
    (Codes are salted hashes, so we check them one by one.)
    """
    conn = sqlite3.connect(VAULT_DB)
    rows = conn.execute("SELECT id, name, code_hash, role FROM users").fetchall()
    conn.close()
    for uid, name, code_hash, role in rows:
        if check_password_hash(code_hash, entered_code):
            return (uid, name, role)
    return None


def require_role(*allowed):
    """If the current role is not among the allowed ones -> 404 (stealthy)."""
    if session.get("role") not in allowed:
        abort(404)


def allowed_image(filename):
    """True if the file has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMG


def count_admins():
    """How many admins exist (so we don't delete the last one)."""
    conn = sqlite3.connect(VAULT_DB)
    n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    conn.close()
    return n


def require_login():
    """Allows ANY logged-in user (admin/manager/simple); otherwise 404."""
    require_role("admin", "manager", "simple")


def encrypt_order(data):
    """Takes an order dict -> encrypted text (Fernet)."""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(raw).decode("utf-8")


def decrypt_order(token):
    """Takes encrypted text -> order dict."""
    raw = fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def cart_summary():
    """
    Reads the cart from the session AND the current prices from the database
    (we never trust prices coming from the browser).
    Returns: (items, total, count)
    """
    cart = session.get("cart", {})
    items, total, count = [], 0.0, 0
    if cart:
        conn = sqlite3.connect(VAULT_DB)
        for pid_str, qty in cart.items():
            row = conn.execute(
                "SELECT id, name, price, image_file FROM products WHERE id=?",
                (int(pid_str),)
            ).fetchone()
            if row:  # if the manager deleted the product, just skip it
                line = row[2] * qty
                total += line
                count += qty
                items.append({"id": row[0], "name": row[1], "price": row[2],
                              "image": row[3], "qty": qty, "line": line})
        conn.close()
    return items, total, count


# ======================================================================
#  CALCULATOR + HIDDEN DOOR
# ======================================================================

def _calculator_inner(result_text):
    """Builds the calculator HTML (result_text goes into the display)."""
    return f"""
    <div class="stage">
        <form method="post" class="device reveal">
            <div class="device__top">
                <div class="brand">Calc<span style="color:var(--amber)">.</span></div>
                <span class="mono" style="font-size:.6rem;letter-spacing:.22em;color:var(--paper-dim)">MOD · CX-7</span>
            </div>
            <div class="display">{html.escape(result_text) or '0'}</div>
            <div class="inputs">
                <input name="num1" inputmode="decimal" placeholder="First number" required autofocus>
                <input name="num2" inputmode="decimal" placeholder="Second number" required>
            </div>
            <div class="keys">
                <button class="key" type="submit" name="op" value="+">+</button>
                <button class="key" type="submit" name="op" value="-">−</button>
                <button class="key" type="submit" name="op" value="*">×</button>
                <button class="key" type="submit" name="op" value="/">÷</button>
            </div>
        </form>
    </div>
    """


@app.route("/", methods=["GET", "POST"])
def calculator():
    result_text = ""
    if request.method == "POST":
        num1_raw = request.form["num1"]
        num2_raw = request.form["num2"]
        op = request.form["op"]

        # --- HIDDEN DOOR ---
        # If "-" was pressed, check the role of the first number:
        #   "admin" -> the number that opens the door: go to the code page
        #   "decoy" -> decoy: send them back to the home page (as if nothing happened)
        if op == "-":
            role = secret_number_role(num1_raw)
            if role == "admin":
                return redirect(url_for("secret"))
            elif role == "decoy":
                return redirect(url_for("calculator"))

        # Decimals with a comma (3,5) or a dot (3.5) both work.
        try:
            num1 = float(num1_raw.replace(",", "."))
            num2 = float(num2_raw.replace(",", "."))
        except ValueError:
            # Bad input (empty/text) -> don't crash, show a message.
            result_text = "Numbers only"
            return page("Calculator", _calculator_inner(result_text))

        if op == "+":
            answer = num1 + num2
        elif op == "-":
            answer = num1 - num2
        elif op == "*":
            answer = num1 * num2
        elif op == "/":
            answer = num1 / num2 if num2 != 0 else "Can't divide by 0"
        else:
            answer = "Unknown operation"

        result_text = str(answer)

    return page("Calculator", _calculator_inner(result_text))


@app.route("/secret", methods=["GET", "POST"])
def secret():
    message = ""
    if request.method == "POST":
        entered = request.form.get("password", "")
        user = lookup_user(entered)
        if user:
            uid, name, role = user
            # Correct code -> give the "wristband" (session) and go
            # to the page that matches their role.
            session["user_id"] = uid
            session["name"] = name
            session["role"] = role
            if role == "admin":
                return redirect(url_for("admin"))
            elif role == "manager":
                return redirect(url_for("manager"))
            else:
                return redirect(url_for("user_page"))
        message = '<div class="notice notice--bad">Wrong code!</div>'

    inner = f"""
    <div class="stage">
        <div class="panel brackets reveal" style="width:100%;max-width:410px">
            <div class="panel__body" style="text-align:center">
                <div class="lock">🔒</div>
                <div class="eyebrow eyebrow--c" style="margin:.9rem 0 .9rem">Restricted · Access</div>
                <h1 style="font-size:2rem;margin-bottom:.4rem">Secret Page</h1>
                <p style="color:var(--paper-dim);font-size:.92rem;margin-bottom:1.4rem">Enter your personal code.</p>
                {message}
                <form method="post">
                    <input type="password" name="password" placeholder="Code" required autofocus style="text-align:center;margin-bottom:1rem">
                    <button type="submit" class="btn btn--accent btn--block">Enter →</button>
                </form>
            </div>
        </div>
        <a href="/" class="backlink reveal">← Back</a>
    </div>
    """
    return page("Access", inner)


# ======================================================================
#  ADMIN — user (code) management
# ======================================================================

def render_admin(message=""):
    """Builds the admin page HTML (dashboard + user list + create form)."""
    conn = sqlite3.connect(VAULT_DB)
    users = conn.execute(
        "SELECT id, name, role, created_at FROM users ORDER BY id"
    ).fetchall()
    n_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    order_rows = conn.execute("SELECT data_enc FROM orders").fetchall()
    conn.close()

    # --- Dashboard stats ---
    n_users = len(users)
    n_orders = len(order_rows)
    revenue = 0.0
    for (enc,) in order_rows:
        try:  # revenue is encrypted -> decrypt it to sum it up
            revenue += float(decrypt_order(enc).get("total", 0))
        except Exception:
            pass

    rows = ""
    for uid, name, role, created_at in users:
        if uid == session.get("user_id"):
            delete_btn = '<span class="mono" style="font-size:.7rem;color:var(--paper-dim)">(you)</span>'
        else:
            delete_btn = (
                f'<form method="post" action="/admin/delete/{uid}" '
                f"onsubmit=\"return confirm('Delete for sure?');\">"
                f'<button class="btn btn--danger" type="submit">Delete</button></form>'
            )
        rows += f"""
            <tr>
                <td style="font-weight:600">{html.escape(name or '')}</td>
                <td><span class="badge badge--{role}">{role}</span></td>
                <td class="mono" style="color:var(--paper-dim);font-size:.8rem">{created_at or ''}</td>
                <td style="text-align:right">{delete_btn}</td>
            </tr>"""

    msg_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""

    inner = f"""
    <div class="wrap wrap--narrow">
        <div class="topbar">
            <div>
                <div class="eyebrow">Admin · Management</div>
                <h1>Control Panel</h1>
            </div>
            <a href="/logout" class="btn btn--ghost">Log out</a>
        </div>

        <div class="stats">
            <div class="stat reveal"><div class="stat__num">{n_users}</div><div class="stat__label">Users</div></div>
            <div class="stat reveal"><div class="stat__num">{n_products}</div><div class="stat__label">Products</div></div>
            <div class="stat reveal"><div class="stat__num">{n_orders}</div><div class="stat__label">Orders</div></div>
            <div class="stat reveal stat--accent"><div class="stat__num">{revenue:.2f} €</div><div class="stat__label">Revenue</div></div>
        </div>

        <div class="panel reveal" style="margin-bottom:1.6rem">
            <div class="panel__head">＋ New user / code</div>
            <div class="panel__body">
                {msg_html}
                <form method="post" action="/admin/create" class="formline formline--users">
                    <input name="name" placeholder="Name / label" required>
                    <select name="role">
                        <option value="manager">manager — uploads products</option>
                        <option value="simple">simple — views products</option>
                    </select>
                    <input name="password" placeholder="Code (≥6)" required>
                    <button class="btn btn--accent" type="submit">Create</button>
                </form>
            </div>
        </div>

        <div class="panel reveal">
            <div class="panel__head">👥 Users with a code</div>
            <table class="table">
                <thead><tr><th>Name</th><th>Role</th><th>Created</th><th></th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
    """
    return page("Admin", inner)


@app.route("/admin")
def admin():
    require_role("admin")
    return render_admin()


@app.route("/admin/create", methods=["POST"])
def admin_create():
    require_role("admin")
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "")
    password = request.form.get("password", "")

    # --- Safety / validity checks ---
    if role not in ("manager", "simple"):
        return render_admin("Invalid role.")
    if not name:
        return render_admin("Enter a name/label.")
    if len(password) < 6:
        return render_admin("The code must be at least 6 characters.")
    if lookup_user(password) is not None:
        return render_admin("This code is already in use — choose another.")

    conn = sqlite3.connect(VAULT_DB)
    conn.execute(
        "INSERT INTO users (name, code_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (name, generate_password_hash(password), role,
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/delete/<int:user_id>", methods=["POST"])
def admin_delete(user_id):
    require_role("admin")
    conn = sqlite3.connect(VAULT_DB)
    row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    # Don't allow deleting the last admin (otherwise we lock ourselves out).
    if row and row[0] == "admin" and count_admins() <= 1:
        conn.close()
        return render_admin("You can't delete the last admin!")
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


# ======================================================================
#  MANAGER — product management
# ======================================================================

def render_manager(message=""):
    """HTML of the manager page: add form + their own products."""
    conn = sqlite3.connect(VAULT_DB)
    products = conn.execute(
        "SELECT id, name, price, description, image_file FROM products "
        "WHERE manager_id=? ORDER BY id DESC",
        (session.get("user_id"),)
    ).fetchall()
    conn.close()

    cards = ""
    for pid, name, price, description, image_file in products:
        cards += f"""
            <div class="product reveal">
                <img class="product__img" src="/static/uploads/{html.escape(image_file or '')}" alt="">
                <div class="product__body">
                    <div class="product__name">{html.escape(name or '')}</div>
                    <div class="tag">{price:.2f} €</div>
                    <div class="product__desc">{html.escape(description or '')}</div>
                    <form method="post" action="/manager/delete-product/{pid}"
                          onsubmit="return confirm('Delete this product for sure?');">
                        <button class="btn btn--danger btn--block" type="submit">Delete</button>
                    </form>
                </div>
            </div>"""
    products_html = f'<div class="grid">{cards}</div>' if cards else \
        '<div class="empty">No products uploaded yet.</div>'

    msg_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""

    inner = f"""
    <div class="wrap">
        <div class="topbar">
            <div>
                <div class="eyebrow">Manager · Inventory</div>
                <h1>My products</h1>
            </div>
            <a href="/logout" class="btn btn--ghost">Log out</a>
        </div>

        <div class="panel reveal" style="margin-bottom:1.8rem">
            <div class="panel__head">＋ New product</div>
            <div class="panel__body">
                {msg_html}
                <form method="post" action="/manager/add-product" enctype="multipart/form-data" class="formline formline--products">
                    <input name="name" placeholder="Product name" required>
                    <input name="price" type="number" step="0.01" min="0" placeholder="Price €" required>
                    <input name="description" placeholder="Description (optional)">
                    <input name="image" type="file" accept="image/*" required>
                    <button class="btn btn--accent" type="submit">Add</button>
                </form>
            </div>
        </div>

        {products_html}
    </div>
    """
    return page("Manager", inner)


@app.route("/manager")
def manager():
    require_role("admin", "manager")
    return render_manager()


@app.route("/manager/add-product", methods=["POST"])
def add_product():
    require_role("admin", "manager")
    name = request.form.get("name", "").strip()
    price_raw = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    image = request.files.get("image")

    # --- Checks ---
    if not name:
        return render_manager("Enter a product name.")
    try:
        price = float(price_raw)
    except ValueError:
        return render_manager("Price must be a number.")
    if image is None or image.filename == "":
        return render_manager("Choose an image.")
    if not allowed_image(image.filename):
        return render_manager("Only images allowed (png, jpg, jpeg, gif, webp).")

    # Safe & unique filename, so images don't overwrite each other.
    ext = image.filename.rsplit(".", 1)[1].lower()
    saved_name = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    image.save(os.path.join(UPLOAD_DIR, saved_name))

    conn = sqlite3.connect(VAULT_DB)
    conn.execute(
        "INSERT INTO products (manager_id, name, price, description, image_file, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], name, price, description, saved_name,
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()
    return redirect(url_for("manager"))


@app.route("/manager/delete-product/<int:pid>", methods=["POST"])
def delete_product(pid):
    require_role("admin", "manager")
    conn = sqlite3.connect(VAULT_DB)
    row = conn.execute(
        "SELECT manager_id, image_file FROM products WHERE id=?", (pid,)
    ).fetchone()
    # A manager deletes ONLY their own (an admin deletes any).
    if row is None or (session.get("role") != "admin" and row[0] != session.get("user_id")):
        conn.close()
        abort(404)
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    # Also delete the image file from disk.
    if row[1]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row[1]))
        except OSError:
            pass
    return redirect(url_for("manager"))


# ======================================================================
#  SIMPLE — product storefront
# ======================================================================

@app.route("/user")
def user_page():
    # Any logged-in user (admin/manager/simple) can see the storefront.
    require_login()

    # Search: ?q=... filters by name or description.
    q = request.args.get("q", "").strip()
    sql = ("SELECT p.id, p.name, p.price, p.description, p.image_file, u.name "
           "FROM products p LEFT JOIN users u ON p.manager_id = u.id")
    params = ()
    if q:
        sql += " WHERE p.name LIKE ? OR p.description LIKE ?"
        params = (f"%{q}%", f"%{q}%")
    sql += " ORDER BY p.id DESC"

    conn = sqlite3.connect(VAULT_DB)
    products = conn.execute(sql, params).fetchall()
    conn.close()

    _, _, count = cart_summary()
    badge = f'<span class="cart-count">{count}</span>' if count else ""

    cards = ""
    for pid, name, price, description, image_file, manager_name in products:
        cards += f"""
            <div class="product reveal">
                <img class="product__img" src="/static/uploads/{html.escape(image_file or '')}" alt="">
                <div class="product__body">
                    <div class="product__name">{html.escape(name or '')}</div>
                    <div class="tag">{price:.2f} €</div>
                    <div class="product__desc">{html.escape(description or '')}</div>
                    <div class="product__meta">— {html.escape(manager_name or '—')}</div>
                    <form method="post" action="/cart/add/{pid}">
                        <button class="btn btn--accent btn--block" type="submit">＋ Add to cart</button>
                    </form>
                </div>
            </div>"""
    if cards:
        products_html = f'<div class="grid grid--shop">{cards}</div>'
    elif q:
        products_html = f'<div class="empty">No products found for &laquo;{html.escape(q)}&raquo;. <a href="/user" style="color:var(--amber)">See all</a></div>'
    else:
        products_html = '<div class="empty">No products yet.</div>'

    clear = f'<a href="/user" class="btn btn--ghost">✕</a>' if q else ""

    inner = f"""
    <div class="wrap">
        <div class="topbar">
            <div>
                <div class="eyebrow">Catalog · Products</div>
                <h1>Products</h1>
            </div>
            <div class="navbtns">
                <a href="/orders" class="btn btn--ghost">My orders</a>
                <a href="/cart" class="btn">🛒 Cart {badge}</a>
                <a href="/logout" class="btn btn--ghost">Log out</a>
            </div>
        </div>
        <form method="get" action="/user" class="searchbar">
            <input name="q" value="{html.escape(q)}" placeholder="Search products...">
            <button class="btn btn--accent" type="submit">Search</button>
            {clear}
        </form>
        {products_html}
    </div>
    """
    return page("Products", inner)


# ======================================================================
#  CART + ORDERS (encrypted)
# ======================================================================

@app.route("/cart/add/<int:pid>", methods=["POST"])
def cart_add(pid):
    require_login()
    conn = sqlite3.connect(VAULT_DB)
    exists = conn.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if exists:
        cart = session.get("cart", {})
        cart[str(pid)] = cart.get(str(pid), 0) + 1
        session["cart"] = cart            # re-assign -> the session gets saved
    return redirect(url_for("cart_view"))


@app.route("/cart/inc/<int:pid>", methods=["POST"])
def cart_inc(pid):
    require_login()
    cart = session.get("cart", {})
    if str(pid) in cart:
        cart[str(pid)] += 1
        session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/dec/<int:pid>", methods=["POST"])
def cart_dec(pid):
    require_login()
    cart = session.get("cart", {})
    if str(pid) in cart:
        cart[str(pid)] -= 1
        if cart[str(pid)] <= 0:
            del cart[str(pid)]
        session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/remove/<int:pid>", methods=["POST"])
def cart_remove(pid):
    require_login()
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart")
def cart_view():
    require_login()
    items, total, count = cart_summary()

    rows = ""
    for it in items:
        rows += f"""
            <div class="cart-row">
                <img class="cart-thumb" src="/static/uploads/{html.escape(it['image'] or '')}" alt="">
                <div class="cart-info">
                    <div class="product__name" style="font-size:1.05rem">{html.escape(it['name'])}</div>
                    <div class="product__meta">{it['price']:.2f} € / ea.</div>
                </div>
                <div class="stepper">
                    <form method="post" action="/cart/dec/{it['id']}"><button class="step" type="submit">−</button></form>
                    <span class="qty mono">{it['qty']}</span>
                    <form method="post" action="/cart/inc/{it['id']}"><button class="step" type="submit">+</button></form>
                </div>
                <div class="tag" style="min-width:95px;text-align:right">{it['line']:.2f} €</div>
                <form method="post" action="/cart/remove/{it['id']}"><button class="btn btn--danger" type="submit">✕</button></form>
            </div>"""

    if items:
        body = f"""
        <div class="panel reveal">
            <div class="panel__body">
                {rows}
                <div class="cart-foot">
                    <a href="/user" class="btn btn--ghost">← Continue shopping</a>
                    <div class="grand">Total: <b>{total:.2f} €</b></div>
                    <a href="/checkout" class="btn btn--accent">Checkout →</a>
                </div>
            </div>
        </div>"""
    else:
        body = """
        <div class="empty">Your cart is empty.</div>
        <div style="margin-top:1.2rem"><a href="/user" class="btn btn--accent">← See the products</a></div>"""

    inner = f"""
    <div class="wrap wrap--narrow">
        <div class="topbar">
            <div>
                <div class="eyebrow">Shop · Cart</div>
                <h1>My cart</h1>
            </div>
            <a href="/user" class="btn btn--ghost">Back to products</a>
        </div>
        {body}
    </div>
    """
    return page("Cart", inner)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    require_login()
    items, total, count = cart_summary()
    if not items:
        return redirect(url_for("cart_view"))

    message = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name or not address or not phone:
            message = "Fill in all the shipping details."
        else:
            # Build the order and ENCRYPT it before storing.
            order = {
                "items": [{"name": it["name"], "price": it["price"],
                           "qty": it["qty"], "line": it["line"]} for it in items],
                "total": round(total, 2),
                "shipping": {"name": name, "address": address, "phone": phone},
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            conn = sqlite3.connect(VAULT_DB)
            conn.execute(
                "INSERT INTO orders (user_id, data_enc, created_at) VALUES (?, ?, ?)",
                (session["user_id"], encrypt_order(order), order["datetime"])
            )
            conn.commit()
            conn.close()
            session["cart"] = {}   # empty the cart after the purchase
            return redirect(url_for("orders_view", ok=1))

    summary = ""
    for it in items:
        summary += f'<li>{html.escape(it["name"])} × {it["qty"]} — {it["line"]:.2f} €</li>'

    msg_html = f'<div class="notice notice--bad">{html.escape(message)}</div>' if message else ""

    inner = f"""
    <div class="wrap wrap--narrow">
        <div class="topbar">
            <div>
                <div class="eyebrow">Payment · Checkout</div>
                <h1>Shipping details</h1>
            </div>
            <a href="/cart" class="btn btn--ghost">← Cart</a>
        </div>
        <div class="checkout-grid">
            <div class="panel reveal">
                <div class="panel__head">🚚 Where to ship</div>
                <div class="panel__body">
                    {msg_html}
                    <form method="post" class="ship-form">
                        <input name="name" placeholder="Full name" required>
                        <input name="address" placeholder="Address (street, city, ZIP)" required>
                        <input name="phone" placeholder="Phone" required>
                        <button class="btn btn--accent btn--block" type="submit">Place order 🔒</button>
                        <p class="product__meta" style="text-align:center">The order is stored encrypted.</p>
                    </form>
                </div>
            </div>
            <div class="panel reveal">
                <div class="panel__head">🧾 Summary</div>
                <div class="panel__body">
                    <ul class="order-list">{summary}</ul>
                    <div class="cart-foot" style="margin-top:1.2rem">
                        <span class="product__meta">{count} items</span>
                        <div class="grand">Total: <b>{total:.2f} €</b></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    return page("Checkout", inner)


@app.route("/orders")
def orders_view():
    require_login()
    conn = sqlite3.connect(VAULT_DB)
    rows = conn.execute(
        "SELECT data_enc, created_at FROM orders WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    ok = request.args.get("ok")
    msg = ('<div class="notice" style="border-color:rgba(94,197,182,.5);color:var(--teal)">'
           '✓ Your order has been placed!</div>') if ok else ""

    cards = ""
    for data_enc, created_at in rows:
        try:
            o = decrypt_order(data_enc)   # decrypt for display
        except Exception:
            continue
        lines = "".join(
            f'<li>{html.escape(i["name"])} × {i["qty"]} — {i["line"]:.2f} €</li>'
            for i in o.get("items", [])
        )
        sh = o.get("shipping", {})
        cards += f"""
            <div class="panel reveal" style="margin-bottom:1.2rem">
                <div class="panel__head">🧾 {created_at} · Total {o.get('total', 0):.2f} €</div>
                <div class="panel__body">
                    <ul class="order-list">{lines}</ul>
                    <div class="product__meta" style="margin-top:.8rem">
                        Shipping: {html.escape(sh.get('name', ''))} · {html.escape(sh.get('address', ''))} · {html.escape(sh.get('phone', ''))}
                    </div>
                </div>
            </div>"""
    body = cards or '<div class="empty">You have no orders yet.</div>'

    inner = f"""
    <div class="wrap wrap--narrow">
        <div class="topbar">
            <div>
                <div class="eyebrow">History · Orders</div>
                <h1>My orders</h1>
            </div>
            <a href="/user" class="btn btn--ghost">Back to products</a>
        </div>
        {msg}
        {body}
    </div>
    """
    return page("Orders", inner)


@app.route("/logout")
def logout():
    # Throws away the "wristband" -> re-locks the hidden pages.
    session.clear()
    return redirect(url_for("calculator"))


if __name__ == "__main__":
    app.run(debug=True)
