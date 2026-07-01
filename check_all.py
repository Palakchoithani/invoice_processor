import firebase_admin
from firebase_admin import credentials, firestore
import os
from config.db_config import FIREBASE_KEY_PATH

def check_all():
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
    collections = db.collections()
    for coll in collections:
        docs = coll.get()
        print(f"Collection {coll.id} has {len(docs)} documents.")

if __name__ == "__main__":
    check_all()
