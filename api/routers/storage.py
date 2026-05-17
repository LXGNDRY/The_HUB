"""
Cloud Storage router — bucket and object management.
"""

from fastapi import APIRouter, HTTPException
from auth.credentials import get_credentials

router = APIRouter()


def _storage():
    from modules.storage import StorageModule
    return StorageModule(get_credentials())


@router.get("/buckets")
def list_buckets():
    """List all GCS buckets in the project."""
    try:
        return [{"name": b.name, "location": b.location} for b in _storage().list_buckets()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
