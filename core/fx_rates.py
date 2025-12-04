"""Foreign exchange rates service with API integration and caching."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Optional

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.config import settings
from models.fx_rates import FxRate


class FxRateService:
    """Service for managing foreign exchange rates."""

    def __init__(self):
        self.api_key = settings.fx_api_key
        self.api_url = settings.fx_api_url
        self.redis: Optional[aioredis.Redis] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def init_redis(self):
        """Initialize Redis connection."""
        self.redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close_redis(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close_http_client(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def get_rate(
        self,
        from_currency: str,
        to_currency: str,
        session: AsyncSession,
        target_date: Optional[date] = None,
    ) -> Decimal:
        """
        Get exchange rate from one currency to another.

        Args:
            from_currency: Source currency code (e.g., 'RSD')
            to_currency: Target currency code (e.g., 'EUR')
            session: Database session
            target_date: Date for the rate (default: today)

        Returns:
            Exchange rate as Decimal

        Raises:
            ValueError: If rate cannot be obtained
        """
        if from_currency == to_currency:
            return Decimal("1.0")

        if target_date is None:
            target_date = date.today()

        # Try cache first
        rate = await self._get_from_cache(from_currency, to_currency, target_date)
        if rate is not None:
            return rate

        # Try database
        rate = await self._get_from_db(from_currency, to_currency, target_date, session)
        if rate is not None:
            await self._save_to_cache(from_currency, to_currency, target_date, rate)
            return rate

        # Fetch from API
        rate = await self._fetch_from_api(from_currency, to_currency, target_date)
        if rate is not None:
            # Save to both cache and DB
            await self._save_to_cache(from_currency, to_currency, target_date, rate)
            await self._save_to_db(from_currency, to_currency, target_date, rate, session)
            return rate

        raise ValueError(f"Cannot get exchange rate for {from_currency} -> {to_currency}")

    async def _get_from_cache(
        self, from_currency: str, to_currency: str, target_date: date
    ) -> Optional[Decimal]:
        """Get rate from Redis cache."""
        if not self.redis:
            return None

        cache_key = f"fx:{from_currency}:{to_currency}:{target_date}"
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for {cache_key}")
                return Decimal(cached)
        except Exception as e:
            logger.warning(f"Redis error: {e}")

        return None

    async def _save_to_cache(
        self, from_currency: str, to_currency: str, target_date: date, rate: Decimal
    ):
        """Save rate to Redis cache (24 hours TTL)."""
        if not self.redis:
            return

        cache_key = f"fx:{from_currency}:{to_currency}:{target_date}"
        try:
            await self.redis.setex(cache_key, 86400, str(rate))  # 24 hours
            logger.debug(f"Cached {cache_key} = {rate}")
        except Exception as e:
            logger.warning(f"Redis error: {e}")

    async def _get_from_db(
        self, from_currency: str, to_currency: str, target_date: date, session: AsyncSession
    ) -> Optional[Decimal]:
        """Get rate from database."""
        try:
            # Try to get rate for the exact date or the closest previous date
            stmt = (
                select(FxRate)
                .where(
                    FxRate.currency == from_currency,
                    FxRate.base == to_currency,
                    FxRate.date <= target_date,
                )
                .order_by(FxRate.date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            fx_rate = result.scalar_one_or_none()

            if fx_rate:
                logger.debug(f"DB hit for {from_currency}/{to_currency} on {fx_rate.date}")
                return fx_rate.rate

        except Exception as e:
            logger.error(f"Database error: {e}")

        return None

    async def _save_to_db(
        self,
        from_currency: str,
        to_currency: str,
        target_date: date,
        rate: Decimal,
        session: AsyncSession,
    ):
        """Save rate to database."""
        try:
            fx_rate = FxRate(
                currency=from_currency,
                base=to_currency,
                rate=rate,
                date=target_date,
            )
            session.add(fx_rate)
            await session.commit()
            logger.debug(f"Saved to DB: {from_currency}/{to_currency} = {rate}")
        except Exception as e:
            logger.error(f"Error saving to DB: {e}")
            await session.rollback()

    async def _fetch_from_api(
        self, from_currency: str, to_currency: str, target_date: date
    ) -> Optional[Decimal]:
        """Fetch rate from exchangerate-api.io."""
        try:
            # exchangerate-api.io URL format
            url = f"{self.api_url}/{self.api_key}/pair/{from_currency}/{to_currency}"

            response = await self.http_client.get(url)
            response.raise_for_status()

            data = response.json()

            if data.get("result") == "success":
                rate = Decimal(str(data["conversion_rate"]))
                logger.info(f"API fetched {from_currency}/{to_currency} = {rate}")
                return rate
            else:
                logger.error(f"API error: {data.get('error-type')}")

        except Exception as e:
            logger.error(f"Error fetching from API: {e}")

        return None

    async def get_rates_for_transaction(
        self, currency: str, session: AsyncSession, target_date: Optional[date] = None
    ) -> Dict[str, Decimal]:
        """
        Get EUR and USD rates for a transaction.

        Args:
            currency: Transaction currency
            session: Database session
            target_date: Date for the rates (default: today)

        Returns:
            Dict with 'eur' and 'usd' rates
        """
        eur_rate = await self.get_rate(currency, "EUR", session, target_date=target_date)
        usd_rate = await self.get_rate(currency, "USD", session, target_date=target_date)

        return {
            "eur": eur_rate,
            "usd": usd_rate,
        }


# Global instance
fx_service = FxRateService()

