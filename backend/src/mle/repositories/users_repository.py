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
        permissions: list[str] | None = None,
    ) -> User:
        u = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name.strip()[:160] or "Usuario",
            role=role if role in ("admin", "user") else "user",
            permissions=permissions or [],
            is_active=True,
        )
        self.session.add(u)
        await self.session.commit()
        await self.session.refresh(u)
        return u

    async def update(
        self,
        user_id: UUID,
        *,
        email: str | None = None,
        display_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        permissions: list[str] | None = None,
    ) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        if email is not None:
            user.email = email.strip().lower()
        if display_name is not None:
            user.display_name = display_name.strip()[:160] or user.display_name
        if role is not None and role in ("admin", "user"):
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if permissions is not None:
            user.permissions = permissions
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: UUID) -> bool:
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True
