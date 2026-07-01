import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
from config.db_config import FIREBASE_KEY_PATH

def query_db():
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
    docs = db.collection("invoices").get()
    print(f"Total invoices without order_by: {len(docs)}")
    for doc in docs:
        print(doc.id, doc.to_dict().get("invoice_number"))

if __name__ == "__main__":
    query_db()
