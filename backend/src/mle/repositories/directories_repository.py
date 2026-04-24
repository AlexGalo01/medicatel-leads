from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import Directory, DirectoryStep, Opportunity
from mle.schemas.directories import (
    DirectoryRead,
    DirectoryStepCreate,
    DirectoryStepRead,
)


class DirectoriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- Directory ----------

    async def create(
        self,
        *,
        name: str,
        description: str | None,
        created_by_user_id: UUID | None,
        steps: list[DirectoryStepCreate],
    ) -> Directory:
        directory = Directory(
            name=name,
            description=description,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(directory)
        await self.session.flush()  # obtener id sin commit aún
        for order, step_data in enumerate(steps):
            step = DirectoryStep(
                directory_id=directory.id,
                name=step_data.name,
                display_order=order,
                is_terminal=step_data.is_terminal,
                is_won=step_data.is_won,
            )
            self.session.add(step)
        await self.session.commit()
        await self.session.refresh(directory)
        return directory

    async def get(self, directory_id: UUID) -> Directory | None:
        return await self.session.get(Directory, directory_id)

    async def list_all(self) -> list[Directory]:
        result = await self.session.execute(
            select(Directory).order_by(Directory.created_at.asc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        directory_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Directory | None:
        directory = await self.session.get(Directory, directory_id)
        if directory is None:
            return None
        if name is not None:
            directory.name = name
        if description is not None:
            directory.description = description
        directory.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(directory)
        return directory

    async def delete(self, directory_id: UUID) -> bool:
        directory = await self.session.get(Directory, directory_id)
        if directory is None:
            return False
        # Prevenir borrado si tiene items.
        count_items = await self.session.execute(
            select(func.count(Opportunity.id)).where(Opportunity.directory_id == directory_id)
        )
        if int(count_items.scalar() or 0) > 0:
            return False
        # Eliminar steps primero.
        steps = await self.session.execute(
            select(DirectoryStep).where(DirectoryStep.directory_id == directory_id)
        )
        for step in steps.scalars().all():
            await self.session.delete(step)
        await self.session.delete(directory)
        await self.session.commit()
        return True

    # ---------- Steps ----------

    async def list_steps(self, directory_id: UUID) -> list[DirectoryStep]:
        result = await self.session.execute(
            select(DirectoryStep)
            .where(DirectoryStep.directory_id == directory_id)
            .order_by(DirectoryStep.display_order.asc())
        )
        return list(result.scalars().all())

    async def add_step(
        self,
        directory_id: UUID,
        *,
        name: str,
        is_terminal: bool = False,
        is_won: bool = False,
    ) -> DirectoryStep:
        existing = await self.list_steps(directory_id)
        next_order = (existing[-1].display_order + 1) if existing else 0
        step = DirectoryStep(
            directory_id=directory_id,
            name=name,
            display_order=next_order,
            is_terminal=is_terminal,
            is_won=is_won,
        )
        self.session.add(step)
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def update_step(
        self,
        step_id: UUID,
        *,
        name: str | None = None,
        is_terminal: bool | None = None,
        is_won: bool | None = None,
        display_order: int | None = None,
    ) -> DirectoryStep | None:
        step = await self.session.get(DirectoryStep, step_id)
        if step is None:
            return None
        if name is not None:
            step.name = name
        if is_terminal is not None:
            step.is_terminal = is_terminal
        if is_won is not None:
            step.is_won = is_won
        if display_order is not None:
            step.display_order = display_order
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def reorder_steps(self, directory_id: UUID, step_ids: list[UUID]) -> list[DirectoryStep]:
        steps = await self.list_steps(directory_id)
        step_map = {s.id: s for s in steps}
        for new_order, step_id in enumerate(step_ids):
            step = step_map.get(step_id)
            if step is not None:
                step.display_order = new_order
        await self.session.commit()
        return await self.list_steps(directory_id)

    async def delete_step(
        self,
        step_id: UUID,
        *,
        move_items_to_step_id: UUID | None = None,
    ) -> bool:
        step = await self.session.get(DirectoryStep, step_id)
        if step is None:
            return False
        # Contar items en el step.
        items_count_result = await self.session.execute(
            select(func.count(Opportunity.id)).where(Opportunity.current_step_id == step_id)
        )
        items_count = int(items_count_result.scalar() or 0)
        if items_count > 0:
            if move_items_to_step_id is None:
                raise ValueError(
                    f"No se puede borrar el step: tiene {items_count} items. Proporciona move_items_to_step_id."
                )
            target = await self.session.get(DirectoryStep, move_items_to_step_id)
            if target is None or target.directory_id != step.directory_id:
                raise ValueError("El step destino debe pertenecer al mismo directorio.")
            # Mover items al target.
            items_result = await self.session.execute(
                select(Opportunity).where(Opportunity.current_step_id == step_id)
            )
            for opp in items_result.scalars().all():
                opp.current_step_id = move_items_to_step_id
                opp.updated_at = datetime.now(timezone.utc)
        await self.session.delete(step)
        await self.session.commit()
        return True

    # ---------- Items (Opportunities) ----------

    async def list_items(self, directory_id: UUID) -> list[Opportunity]:
        result = await self.session.execute(
            select(Opportunity)
            .where(Opportunity.directory_id == directory_id)
            .order_by(Opportunity.updated_at.desc())
        )
        return list(result.scalars().all())

    async def count_items_by_directory(self, directory_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(Opportunity.id)).where(Opportunity.directory_id == directory_id)
        )
        return int(result.scalar() or 0)

    async def first_step(self, directory_id: UUID) -> DirectoryStep | None:
        steps = await self.list_steps(directory_id)
        return steps[0] if steps else None

    # ---------- Opp movement ----------

    async def move_opportunity(self, opportunity_id: UUID, direction: str) -> Opportunity | None:
        """Avanza o retrocede la opp al step adyacente dentro de su directorio."""
        opp = await self.session.get(Opportunity, opportunity_id)
        if opp is None or opp.directory_id is None or opp.current_step_id is None:
            return None
        if opp.terminated_at is not None:
            return None  # opps terminadas no se mueven
        steps = await self.list_steps(opp.directory_id)
        idx = next((i for i, s in enumerate(steps) if s.id == opp.current_step_id), None)
        if idx is None:
            return None
        if direction == "forward":
            target_idx = idx + 1
        elif direction == "backward":
            target_idx = idx - 1
        else:
            return None
        if target_idx < 0 or target_idx >= len(steps):
            return None
        target_step = steps[target_idx]
        opp.current_step_id = target_step.id
        opp.updated_at = datetime.now(timezone.utc)
        # Si el step destino es terminal, auto-terminar la opp.
        if target_step.is_terminal and opp.terminated_at is None:
            opp.terminated_at = opp.updated_at
            opp.terminated_outcome = "won" if target_step.is_won else "lost"
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def terminate_opportunity(
        self,
        opportunity_id: UUID,
        *,
        outcome: str,
        note: str | None,
    ) -> Opportunity | None:
        opp = await self.session.get(Opportunity, opportunity_id)
        if opp is None:
            return None
        opp.terminated_at = datetime.now(timezone.utc)
        opp.terminated_outcome = outcome
        opp.terminated_note = note
        opp.updated_at = opp.terminated_at
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def reopen_opportunity(self, opportunity_id: UUID) -> Opportunity | None:
        opp = await self.session.get(Opportunity, opportunity_id)
        if opp is None:
            return None
        opp.terminated_at = None
        opp.terminated_outcome = None
        opp.terminated_note = None
        opp.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    # ---------- Serialización ----------

    def to_read(self, directory: Directory, steps: list[DirectoryStep], item_count: int) -> DirectoryRead:
        return DirectoryRead(
            id=directory.id,
            name=directory.name,
            description=directory.description,
            created_by_user_id=directory.created_by_user_id,
            steps=[
                DirectoryStepRead(
                    id=s.id,
                    name=s.name,
                    display_order=s.display_order,
                    is_terminal=s.is_terminal,
                    is_won=s.is_won,
                    created_at=s.created_at,
                )
                for s in steps
            ],
            item_count=item_count,
            created_at=directory.created_at,
            updated_at=directory.updated_at,
        )
