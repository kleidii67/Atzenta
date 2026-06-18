# 🧮 Calculator (Flask)

Μια αριθμομηχανή φτιαγμένη με **Flask** + **SQLite**, ως project εκμάθησης Python.

Ο κώδικας βρίσκεται στον φάκελο [`calculatorphone/`](calculatorphone/).

## ▶️ Πώς τρέχει

```bash
# 1) Εγκατάσταση Flask (μία φορά)
pip install flask

# 2) Στήσιμο των βάσεων δεδομένων (μία φορά)
cd calculatorphone
python setup_databases.py

# 3) Εκκίνηση
python calculatorflsk.py
```

Άνοιξε τον browser στο **http://127.0.0.1:5000**

## 🔐 Ασφάλεια

Τα μυστικά δεδομένα **δεν** ανεβαίνουν ποτέ στο GitHub (τα κρύβει το `.gitignore`):

- `secret.key` — το κλειδί που υπογράφει τα sessions
- `*.db` — οι βάσεις δεδομένων
- `static/uploads/` — αρχεία που ανεβάζουν οι χρήστες

> Οι κωδικοί αποθηκεύονται μόνο ως salted hash και ποτέ σε απλό κείμενο.

---
*Φτιάχτηκε με 💛 ως μέρος ενός μαθήματος Python.*
