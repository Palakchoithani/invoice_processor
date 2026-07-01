import firebase_admin
from firebase_admin import credentials, firestore
import os
from config.db_config import FIREBASE_KEY_PATH

if not firebase_admin._apps:
    if os.path.exists(FIREBASE_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()
db = firestore.client()
invoices = db.collection("invoices").get()
print(f"Total invoices: {len(invoices)}")
for inv in invoices:
    data = inv.to_dict()
    print("ID:", inv.id)
    print("Created At:", data.get("created_at"))
    print("Invoice Number:", data.get("invoice_number"))
