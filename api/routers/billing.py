"""
Billing router — spend summary and service breakdown.
"""

from fastapi import APIRouter, HTTPException
from auth.credentials import get_credentials

router = APIRouter()


def _billing():
    from modules.billing import BillingModule
    return BillingModule(get_credentials())


@router.get("/summary")
def billing_summary():
    """Return monthly and daily spend totals."""
    try:
        b = _billing()
        return {
            "monthly_spend": b.get_monthly_spend(),
            "today_spend": b.get_today_spend(),
            "top_services": b.get_top_services(limit=5),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
