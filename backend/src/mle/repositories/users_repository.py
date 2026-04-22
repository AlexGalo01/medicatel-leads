from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import User


class UsersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        q = select(User).where(User.email == email.strip().lower())
        r = await self.session.execute(q)
        return r.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        q = select(User).order_by(User.email.asc())
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        role: str = "user",
    ) -> User:
        u = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name.strip()[:160] or "Usuario",
            role=role if role in ("admin", "user") else "user",
            is_active=True,
        )
        self.session.add(u)
        await self.session.commit()
        await self.session.refresh(u)
        return u
