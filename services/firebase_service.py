import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def save_invoice(data):
    doc_ref = db.collection("invoices").document()
    doc_ref.set(data)
    return doc_ref.id