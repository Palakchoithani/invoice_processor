import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
from config.db_config import FIREBASE_KEY_PATH

def wipe_db():
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
    for coll in ["invoices", "processing_logs", "document_jobs"]:
        docs = db.collection(coll).get()
        for doc in docs:
            db.collection(coll).document(doc.id).delete()
    print("Database wiped!")

if __name__ == "__main__":
    wipe_db()
