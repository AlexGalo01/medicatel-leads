from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import ScrapingSite


class ScrapingSitesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[ScrapingSite]:
        """List all scraping sites."""
        result = await self.session.execute(select(ScrapingSite).order_by(ScrapingSite.created_at.desc()))
        return list(result.scalars().all())

    async def get(self, site_id: UUID) -> ScrapingSite | None:
        """Get a scraping site by ID."""
        return await self.session.get(ScrapingSite, site_id)

    async def create(
        self,
        *,
        url: str,
        title: str = "",
        notes: str | None = None,
        scrape_prompt: str | None = None,
        enrich_prompt: str | None = None,
        created_by_user_id: UUID | None = None,
    ) -> ScrapingSite:
        """Create a new scraping site."""
        site = ScrapingSite(
            url=url.strip(),
            title=title.strip(),
            notes=notes.strip() if notes else None,
            scrape_prompt=scrape_prompt.strip() if scrape_prompt else None,
            enrich_prompt=enrich_prompt.strip() if enrich_prompt else None,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(site)
        await self.session.commit()
        await self.session.refresh(site)
        return site

    async def update(
        self,
        site_id: UUID,
        *,
        title: str | None = None,
        notes: str | None = None,
        scrape_prompt: str | None = None,
        enrich_prompt: str | None = None,
    ) -> ScrapingSite | None:
        """Update a scraping site."""
        site = await self.get(site_id)
        if site is None:
            return None
        if title is not None:
            site.title = title.strip()
        if notes is not None:
            site.notes = notes.strip() if notes else None
        if scrape_prompt is not None:
            site.scrape_prompt = scrape_prompt.strip() if scrape_prompt else None
        if enrich_prompt is not None:
            site.enrich_prompt = enrich_prompt.strip() if enrich_prompt else None
        site.updated_at = datetime.now(timezone.utc)
        self.session.add(site)
        await self.session.commit()
        await self.session.refresh(site)
        return site

    async def set_last_scrape_job(self, site_id: UUID, job_id: UUID) -> None:
        """Update the last scrape job ID for a site."""
        site = await self.get(site_id)
        if site is None:
            return
        site.last_scrape_job_id = job_id
        site.updated_at = datetime.now(timezone.utc)
        self.session.add(site)
        await self.session.commit()

    async def delete(self, site_id: UUID) -> bool:
        """Delete a scraping site."""
        site = await self.get(site_id)
        if site is None:
            return False
        await self.session.delete(site)
        await self.session.commit()
        return True
