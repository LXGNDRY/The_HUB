"""Database-backed atomic webhook replay protection."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import WebhookReceipt


class DatabaseEventStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim(self, provider: str, event_id: str, topic: str = "") -> bool:
        self.db.add(WebhookReceipt(provider=provider, event_id=event_id, topic=topic))
        try:
            await self.db.commit()
            return True
        except IntegrityError:
            await self.db.rollback()
            return False

    async def release(self, provider: str, event_id: str) -> None:
        """Release a failed claim so a provider retry can process it again."""
        await self.db.execute(
            delete(WebhookReceipt).where(
                WebhookReceipt.provider == provider,
                WebhookReceipt.event_id == event_id,
            )
        )
        await self.db.commit()
