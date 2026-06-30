import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent))
load_dotenv()

from services.database import get_db

db = get_db()

def delete_collection(coll_ref, batch_size):
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0

    for doc in docs:
        print(f"Deleting doc {doc.id} => {doc.to_dict()}")
        doc.reference.delete()
        deleted += 1

    if deleted >= batch_size:
        return delete_collection(coll_ref, batch_size)

print("Wiping 'invoices' collection...")
delete_collection(db.collection('invoices'), 50)

print("Wiping 'processing_logs' collection...")
delete_collection(db.collection('processing_logs'), 50)

print("All database data has been deleted.")
