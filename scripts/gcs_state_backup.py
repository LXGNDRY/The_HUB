"""
gcs_state_backup.py
Pull all files from lb-feed-state GCS bucket and save locally as backup.
"""
import json, os, sys
from google.oauth2 import service_account
from google.cloud import storage

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    sys.exit("ERROR: GCP_SA_KEY not set.")

sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(sa_info)
client = storage.Client(credentials=creds, project=sa_info.get("project_id"))

BUCKET_NAME = "lb-feed-state"

print(f"\n=== GCS State Backup: gs://{BUCKET_NAME} ===")

try:
    bucket = client.get_bucket(BUCKET_NAME)
    blobs = list(bucket.list_blobs())
    print(f"  Files found: {len(blobs)}")
    
    os.makedirs("outputs/gcs_backup", exist_ok=True)
    
    for blob in blobs:
        print(f"\n  Downloading: {blob.name} ({blob.size} bytes, updated {blob.updated})")
        content = blob.download_as_text()
        
        # Save to outputs
        safe_name = blob.name.replace("/", "_")
        local_path = f"outputs/gcs_backup/{safe_name}"
        with open(local_path, "w") as f:
            f.write(content)
        print(f"  Saved to: {local_path}")
        
        # Print summary of content
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                keys = list(data.keys())
                print(f"  Keys: {keys}")
                if "products" in data:
                    products = data["products"]
                    locked = sum(1 for p in products.values() if p.get("locked"))
                    total = len(products)
                    last_run = data.get("last_run", "unknown")
                    print(f"  Last run: {last_run}")
                    print(f"  Products tracked: {total}")
                    print(f"  Locked (high performers): {locked}")
                    print(f"  Rotating: {total - locked}")
                    
                    # Show locked products
                    if locked > 0:
                        print(f"\n  LOCKED HIGH-PERFORMER TITLES:")
                        for handle, pdata in products.items():
                            if pdata.get("locked"):
                                print(f"    {handle}")
                                print(f"      title: {pdata.get('current_title','')[:80]}")
                                print(f"      locked_since: {pdata.get('locked_since','?')}")
                                print(f"      ctr: {pdata.get('ctr','?')}")
                    
                    # Show rotation history sample
                    print(f"\n  ROTATION STATE SAMPLE (first 5):")
                    for i, (handle, pdata) in enumerate(list(products.items())[:5]):
                        print(f"    {handle}:")
                        print(f"      prefix_index: {pdata.get('prefix_index', 0)}")
                        print(f"      last_rotated: {pdata.get('last_rotated','never')}")
                        print(f"      locked: {pdata.get('locked', False)}")
        except:
            print(f"  (non-JSON or parse error — raw content saved)")

except Exception as e:
    print(f"  ERROR accessing bucket: {e}")
    
    # Try listing all buckets to find the right name
    print("\n  Listing all accessible buckets...")
    try:
        for bucket in client.list_buckets():
            print(f"    gs://{bucket.name}")
    except Exception as e2:
        print(f"  ERROR listing buckets: {e2}")

print("\nBackup complete.")
