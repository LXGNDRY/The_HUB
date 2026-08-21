"""Database-backed atomic webhook replay protection."""

from sqlalchemy.exc import IntegrityError
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
