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
logs = db.collection("processing_logs").get()
success_logs = [l.to_dict() for l in logs if l.to_dict().get("status") == "SUCCESS"]
print("Success Logs:", len(success_logs))
for l in success_logs:
    print(l.get("file_name"), l.get("processed_at"))
