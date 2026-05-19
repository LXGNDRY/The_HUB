"""
modules/storage.py — Cloud Storage bucket management.
"""

import os
from google.cloud import storage


class StorageModule:
    def __init__(self, credentials=None):
        self.project_id = os.getenv("GCP_PROJECT_ID", "")
        kwargs = {"credentials": credentials, "project": self.project_id} if credentials else {"project": self.project_id}
        self.client = storage.Client(**kwargs)

    def list_buckets(self) -> list:
        return list(self.client.list_buckets())

    def get_bucket_size_bytes(self, bucket_name: str) -> int:
        """Return total size in bytes of all objects in a bucket."""
        bucket = self.client.bucket(bucket_name)
        total = 0
        for blob in self.client.list_blobs(bucket):
            total += blob.size or 0
        return total

    def delete_old_objects(self, bucket_name: str, older_than_days: int = 90) -> list:
        """Delete objects not modified in older_than_days days. Returns list of deleted names."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        bucket = self.client.bucket(bucket_name)
        deleted = []
        for blob in self.client.list_blobs(bucket):
            if blob.updated and blob.updated < cutoff:
                blob.delete()
                deleted.append(blob.name)
        return deleted
