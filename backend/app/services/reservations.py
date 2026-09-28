import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


def to_cents(value) -> Decimal:
    """Round a monetary amount to cents using standard financial rounding."""
    return Decimal(str(value or 0)).quantize(CENTS, rounding=ROUND_HALF_UP)


async def _get_pool():
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise Exception("Database pool not available")
    return db_pool


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month.

    Month boundaries are evaluated in the property's local timezone, so a booking
    checking in at 00:30 on March 1st in Paris counts as March revenue even though
    it is still February 29th in UTC.
    """
    if month < 12:
        next_month, next_year = month + 1, year
    else:
        next_month, next_year = 1, year + 1

    query = text("""
        SELECT
            SUM(r.total_amount) as total_revenue,
            COUNT(r.id) as reservation_count
        FROM reservations r
        JOIN properties p
            ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
        AND r.tenant_id = :tenant_id
        AND (r.check_in_date AT TIME ZONE p.timezone) >= make_timestamp(:year, :month, 1, 0, 0, 0)
        AND (r.check_in_date AT TIME ZONE p.timezone) < make_timestamp(:next_year, :next_month, 1, 0, 0, 0)
    """)

    db_pool = await _get_pool()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
            "next_year": next_year,
            "next_month": next_month,
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(to_cents(row.total_revenue if row else 0)),
        "currency": "USD",
        "count": row.reservation_count if row else 0,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    query = text("""
        SELECT
            property_id,
            SUM(total_amount) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        GROUP BY property_id
    """)

    db_pool = await _get_pool()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(to_cents(row.total_revenue)),
            "currency": "USD",
            "count": row.reservation_count
        }

    # No reservations found for this property in this tenant
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0
    }
