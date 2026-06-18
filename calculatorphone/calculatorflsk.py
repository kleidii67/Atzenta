from flask import Flask, request, redirect, url_for, session, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import html
import uuid
import hashlib
from datetime import datetime

app = Flask(__name__)

# --- Διαδρομές προς τις βάσεις & τον φάκελο εικόνων ---
HERE = os.path.dirname(os.path.abspath(__file__))
NUMBERS_DB = os.path.join(HERE, "combos.db")   # οι μυστικοί αριθμοί
VAULT_DB = os.path.join(HERE, "vault.db")      # χρήστες + προϊόντα
UPLOAD_DIR = os.path.join(HERE, "static", "uploads")  # εικόνες προϊόντων

# Εικόνες: μόνο αυτές οι καταλήξεις επιτρέπονται, μέγιστο μέγεθος 5 MB.
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# --- Μυστικό κλειδί για τα sessions (το "βραχιολάκι") ---
# Φορτώνεται από το αρχείο secret.key. Αν δεν υπάρχει, φτιάχνεται τυχαίο.
# Κρατιέται ΕΚΤΟΣ git (δες .gitignore) ώστε να μένει μυστικό και δύσκολο να σπάσει.
KEY_FILE = os.path.join(HERE, "secret.key")
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        app.secret_key = f.read()
else:
    app.secret_key = os.urandom(32)
    with open(KEY_FILE, "wb") as f:
        f.write(app.secret_key)


# ======================================================================
#  ΕΜΦΑΝΙΣΗ — design system ("Analog Control Room")
#  Ένα κοινό <head> (fonts + CSS) και ένα page() wrapper για ΟΛΕΣ τις σελίδες.
# ======================================================================

GOOGLE_FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,500&family=Hanken+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
"""

# ΣΗΜΑΝΤΙΚΟ: το STYLES ΔΕΝ είναι f-string (το CSS έχει { } που θα μπερδεύονταν).
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

  /* --- Τυπογραφία / helpers --- */
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

  /* --- Layout κεντραρισμένων σελίδων --- */
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
    """Τυλίγει το περιεχόμενο μιας σελίδας με το κοινό <head> + design."""
    return f"""<!doctype html>
<html lang="el">
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
#  ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ
# ======================================================================

def secret_number_role(raw_number):
    """
    Τι ρόλο έχει ο αριθμός που γράφτηκε:
      "admin"  -> ο αριθμός που ΑΝΟΙΓΕΙ ΤΗΝ ΠΟΡΤΑ (πας στη σελίδα κωδικού)
      "decoy"  -> ένας από τους υπόλοιπους μυστικούς (δόλωμα, πάει πίσω)
      None     -> δεν είναι καθόλου μυστικός αριθμός
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
    Ψάχνει ποιος χρήστης έχει αυτόν τον κωδικό.
    Επιστρέφει (id, name, role) αν βρεθεί, αλλιώς None.
    (Οι κωδικοί είναι salted hash, οπότε τους ελέγχουμε έναν-έναν.)
    """
    conn = sqlite3.connect(VAULT_DB)
    rows = conn.execute("SELECT id, name, code_hash, role FROM users").fetchall()
    conn.close()
    for uid, name, code_hash, role in rows:
        if check_password_hash(code_hash, entered_code):
            return (uid, name, role)
    return None


def require_role(*allowed):
    """Αν ο τρέχων ρόλος δεν είναι μέσα στους επιτρεπόμενους -> 404 (κρυφό)."""
    if session.get("role") not in allowed:
        abort(404)


def allowed_image(filename):
    """True αν το αρχείο έχει επιτρεπτή κατάληξη εικόνας."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMG


def count_admins():
    """Πόσοι admin υπάρχουν (για να μην σβήσουμε τον τελευταίο)."""
    conn = sqlite3.connect(VAULT_DB)
    n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    conn.close()
    return n


# ======================================================================
#  ΑΡΙΘΜΟΜΗΧΑΝΗ + ΚΡΥΦΗ ΠΟΡΤΑ
# ======================================================================

@app.route("/", methods=["GET", "POST"])
def calculator():
    result_text = ""
    if request.method == "POST":
        num1_raw = request.form["num1"]
        num2_raw = request.form["num2"]
        op = request.form["op"]

        # --- ΜΥΣΤΙΚΗ ΠΟΡΤΑ ---
        # Αν πατήθηκε το "-", κοίτα τι ρόλο έχει ο πρώτος αριθμός:
        #   "admin" -> ο αριθμός που ανοίγει την πόρτα: πήγαινε στη σελίδα κωδικού
        #   "decoy" -> δόλωμα: πέτα τον πίσω στην αρχική (σαν να μην έγινε τίποτα)
        if op == "-":
            role = secret_number_role(num1_raw)
            if role == "admin":
                return redirect(url_for("secret"))
            elif role == "decoy":
                return redirect(url_for("calculator"))

        num1 = float(num1_raw)
        num2 = float(num2_raw)

        if op == "+":
            answer = num1 + num2
        elif op == "-":
            answer = num1 - num2
        elif op == "*":
            answer = num1 * num2
        elif op == "/":
            answer = num1 / num2
        else:
            answer = "Άγνωστη πράξη"

        result_text = str(answer)

    inner = f"""
    <div class="stage">
        <form method="post" class="device reveal">
            <div class="device__top">
                <div class="brand">Calc<span style="color:var(--amber)">.</span></div>
                <span class="mono" style="font-size:.6rem;letter-spacing:.22em;color:var(--paper-dim)">MOD · CX-7</span>
            </div>
            <div class="display">{html.escape(result_text) or '0'}</div>
            <div class="inputs">
                <input name="num1" inputmode="decimal" placeholder="Πρώτος αριθμός" required autofocus>
                <input name="num2" inputmode="decimal" placeholder="Δεύτερος αριθμός" required>
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
    return page("Calculator", inner)


@app.route("/secret", methods=["GET", "POST"])
def secret():
    message = ""
    if request.method == "POST":
        entered = request.form.get("password", "")
        user = lookup_user(entered)
        if user:
            uid, name, role = user
            # Σωστός κωδικός -> δώσε "βραχιολάκι" (session) και πήγαινε
            # στη σελίδα που ταιριάζει στον ρόλο του.
            session["user_id"] = uid
            session["name"] = name
            session["role"] = role
            if role == "admin":
                return redirect(url_for("admin"))
            elif role == "manager":
                return redirect(url_for("manager"))
            else:
                return redirect(url_for("user_page"))
        message = '<div class="notice notice--bad">Λάθος κωδικός!</div>'

    inner = f"""
    <div class="stage">
        <div class="panel brackets reveal" style="width:100%;max-width:410px">
            <div class="panel__body" style="text-align:center">
                <div class="lock">🔒</div>
                <div class="eyebrow eyebrow--c" style="margin:.9rem 0 .9rem">Restricted · Είσοδος</div>
                <h1 style="font-size:2rem;margin-bottom:.4rem">Μυστική Σελίδα</h1>
                <p style="color:var(--paper-dim);font-size:.92rem;margin-bottom:1.4rem">Δώσε τον προσωπικό σου κωδικό.</p>
                {message}
                <form method="post">
                    <input type="password" name="password" placeholder="Κωδικός" required autofocus style="text-align:center;margin-bottom:1rem">
                    <button type="submit" class="btn btn--accent btn--block">Είσοδος →</button>
                </form>
            </div>
        </div>
        <a href="/" class="backlink reveal">← Πίσω</a>
    </div>
    """
    return page("Είσοδος", inner)


# ======================================================================
#  ADMIN — διαχείριση χρηστών (κωδικών)
# ======================================================================

def render_admin(message=""):
    """Φτιάχνει το HTML της admin σελίδας (λίστα χρηστών + φόρμα δημιουργίας)."""
    conn = sqlite3.connect(VAULT_DB)
    users = conn.execute(
        "SELECT id, name, role, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()

    rows = ""
    for uid, name, role, created_at in users:
        if uid == session.get("user_id"):
            delete_btn = '<span class="mono" style="font-size:.7rem;color:var(--paper-dim)">(εσύ)</span>'
        else:
            delete_btn = (
                f'<form method="post" action="/admin/delete/{uid}" '
                f"onsubmit=\"return confirm('Σίγουρα διαγραφή;');\">"
                f'<button class="btn btn--danger" type="submit">Διαγραφή</button></form>'
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
                <div class="eyebrow">Admin · Διαχείριση</div>
                <h1>Πίνακας ελέγχου</h1>
            </div>
            <a href="/logout" class="btn btn--ghost">Έξοδος</a>
        </div>

        <div class="panel reveal" style="margin-bottom:1.6rem">
            <div class="panel__head">＋ Νέος χρήστης / κωδικός</div>
            <div class="panel__body">
                {msg_html}
                <form method="post" action="/admin/create" class="formline formline--users">
                    <input name="name" placeholder="Όνομα / ετικέτα" required>
                    <select name="role">
                        <option value="manager">manager — ανεβάζει προϊόντα</option>
                        <option value="simple">simple — βλέπει προϊόντα</option>
                    </select>
                    <input name="password" placeholder="Κωδικός (≥6)" required>
                    <button class="btn btn--accent" type="submit">Δημιουργία</button>
                </form>
            </div>
        </div>

        <div class="panel reveal">
            <div class="panel__head">👥 Χρήστες με κωδικό</div>
            <table class="table">
                <thead><tr><th>Όνομα</th><th>Ρόλος</th><th>Δημιουργήθηκε</th><th></th></tr></thead>
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

    # --- Έλεγχοι ασφαλείας/ορθότητας ---
    if role not in ("manager", "simple"):
        return render_admin("Άκυρος ρόλος.")
    if not name:
        return render_admin("Βάλε ένα όνομα/ετικέτα.")
    if len(password) < 6:
        return render_admin("Ο κωδικός πρέπει να έχει τουλάχιστον 6 χαρακτήρες.")
    if lookup_user(password) is not None:
        return render_admin("Αυτός ο κωδικός χρησιμοποιείται ήδη — διάλεξε άλλον.")

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
    # Μην αφήσεις να σβηστεί ο τελευταίος admin (αλλιώς κλειδωνόμαστε έξω).
    if row and row[0] == "admin" and count_admins() <= 1:
        conn.close()
        return render_admin("Δεν μπορείς να σβήσεις τον τελευταίο admin!")
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


# ======================================================================
#  MANAGER — διαχείριση προϊόντων
# ======================================================================

def render_manager(message=""):
    """HTML της manager σελίδας: φόρμα προσθήκης + τα δικά του προϊόντα."""
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
                          onsubmit="return confirm('Σίγουρα διαγραφή προϊόντος;');">
                        <button class="btn btn--danger btn--block" type="submit">Διαγραφή</button>
                    </form>
                </div>
            </div>"""
    products_html = f'<div class="grid">{cards}</div>' if cards else \
        '<div class="empty">Δεν έχεις ανεβάσει προϊόντα ακόμα.</div>'

    msg_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""

    inner = f"""
    <div class="wrap">
        <div class="topbar">
            <div>
                <div class="eyebrow">Manager · Απόθεμα</div>
                <h1>Τα προϊόντα μου</h1>
            </div>
            <a href="/logout" class="btn btn--ghost">Έξοδος</a>
        </div>

        <div class="panel reveal" style="margin-bottom:1.8rem">
            <div class="panel__head">＋ Νέο προϊόν</div>
            <div class="panel__body">
                {msg_html}
                <form method="post" action="/manager/add-product" enctype="multipart/form-data" class="formline formline--products">
                    <input name="name" placeholder="Όνομα προϊόντος" required>
                    <input name="price" type="number" step="0.01" min="0" placeholder="Τιμή €" required>
                    <input name="description" placeholder="Περιγραφή (προαιρετικό)">
                    <input name="image" type="file" accept="image/*" required>
                    <button class="btn btn--accent" type="submit">Προσθήκη</button>
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

    # --- Έλεγχοι ---
    if not name:
        return render_manager("Βάλε όνομα προϊόντος.")
    try:
        price = float(price_raw)
    except ValueError:
        return render_manager("Η τιμή πρέπει να είναι αριθμός.")
    if image is None or image.filename == "":
        return render_manager("Διάλεξε μια εικόνα.")
    if not allowed_image(image.filename):
        return render_manager("Επιτρέπονται μόνο εικόνες (png, jpg, jpeg, gif, webp).")

    # Ασφαλές & μοναδικό όνομα αρχείου, ώστε να μην "πατιούνται" εικόνες.
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
    # Ένας manager σβήνει ΜΟΝΟ τα δικά του (ο admin σβήνει οποιοδήποτε).
    if row is None or (session.get("role") != "admin" and row[0] != session.get("user_id")):
        conn.close()
        abort(404)
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    # Σβήσε και το αρχείο της εικόνας από τον δίσκο.
    if row[1]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row[1]))
        except OSError:
            pass
    return redirect(url_for("manager"))


# ======================================================================
#  SIMPLE — προβολή προϊόντων (βιτρίνα)
# ======================================================================

@app.route("/user")
def user_page():
    # Οποιοσδήποτε συνδεδεμένος (admin/manager/simple) μπορεί να δει τη βιτρίνα.
    require_role("admin", "manager", "simple")

    conn = sqlite3.connect(VAULT_DB)
    products = conn.execute(
        "SELECT p.name, p.price, p.description, p.image_file, u.name "
        "FROM products p LEFT JOIN users u ON p.manager_id = u.id "
        "ORDER BY p.id DESC"
    ).fetchall()
    conn.close()

    cards = ""
    for name, price, description, image_file, manager_name in products:
        cards += f"""
            <div class="product reveal">
                <img class="product__img" src="/static/uploads/{html.escape(image_file or '')}" alt="">
                <div class="product__body">
                    <div class="product__name">{html.escape(name or '')}</div>
                    <div class="tag">{price:.2f} €</div>
                    <div class="product__desc">{html.escape(description or '')}</div>
                    <div class="product__meta">— {html.escape(manager_name or '—')}</div>
                </div>
            </div>"""
    products_html = f'<div class="grid grid--shop">{cards}</div>' if cards else \
        '<div class="empty">Δεν υπάρχουν προϊόντα ακόμα.</div>'

    inner = f"""
    <div class="wrap">
        <div class="topbar">
            <div>
                <div class="eyebrow">Κατάλογος · Products</div>
                <h1>Προϊόντα</h1>
            </div>
            <a href="/logout" class="btn btn--ghost">Έξοδος</a>
        </div>
        {products_html}
    </div>
    """
    return page("Προϊόντα", inner)


@app.route("/logout")
def logout():
    # Πετάει το "βραχιολάκι" -> ξανα-κλειδώνει τις κρυφές σελίδες.
    session.clear()
    return redirect(url_for("calculator"))


if __name__ == "__main__":
    app.run(debug=True)
