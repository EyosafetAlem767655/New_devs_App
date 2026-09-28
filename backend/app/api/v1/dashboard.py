import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Never fall back to a shared/default tenant - that would break isolation
        raise HTTPException(status_code=403, detail="No tenant associated with this user")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except Exception as e:
        logger.error(f"Revenue lookup failed for {property_id} (tenant: {tenant_id}): {e}")
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")

    # Total is already rounded to cents as a Decimal string; convert only at the edge
    total_revenue = round(float(Decimal(revenue_data['total'])), 2)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
