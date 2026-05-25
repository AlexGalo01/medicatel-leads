from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import func, case, text, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from mle.db.models import (
    Directory,
    DirectoryStep,
    Lead,
    Opportunity,
    ScrapingSite,
    SearchJob,
    UrlScrapeJob,
    User,
)


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Pipeline metrics ──────────────────────────────────────────────

    async def get_pipeline_metrics(self) -> dict:
        not_deleted = Opportunity.deleted_at.is_(None)  # type: ignore[union-attr]

        # KPIs
        total = int(
            (await self.session.execute(
                select(func.count(Opportunity.id)).where(not_deleted)
            )).scalar_one()
        )
        active = int(
            (await self.session.execute(
                select(func.count(Opportunity.id)).where(
                    not_deleted, Opportunity.terminated_at.is_(None)  # type: ignore[union-attr]
                )
            )).scalar_one()
        )

        # Won / lost
        terminated_rows = (await self.session.execute(
            select(
                Opportunity.terminated_outcome,
                func.count(Opportunity.id),
            ).where(
                not_deleted,
                Opportunity.terminated_at.isnot(None),
            ).group_by(Opportunity.terminated_outcome)
        )).all()

        won_lost: dict[str, int] = {}
        won_count = 0
        lost_count = 0
        for outcome, cnt in terminated_rows:
            key = outcome or "unknown"
            won_lost[key] = cnt
            # Check if outcome maps to a won step
            if key in ("ganada", "won", "positivo"):
                won_count += cnt
            elif key != "unknown":
                lost_count += cnt

        # Also check via directory_steps.is_won for won count
        won_via_step = int(
            (await self.session.execute(
                select(func.count(Opportunity.id)).where(
                    not_deleted,
                    Opportunity.current_step_id.isnot(None),  # type: ignore[union-attr]
                ).where(
                    Opportunity.current_step_id.in_(  # type: ignore[union-attr]
                        select(DirectoryStep.id).where(
                            DirectoryStep.is_won.is_(True),
                            DirectoryStep.deleted_at.is_(None),  # type: ignore[union-attr]
                        )
                    )
                )
            )).scalar_one()
        )
        if won_via_step > won_count:
            won_count = won_via_step

        terminated_total = won_count + lost_count
        win_rate = (won_count / terminated_total) if terminated_total > 0 else 0.0

        # Opportunities by step
        step_rows = (await self.session.execute(
            select(
                DirectoryStep.id,
                DirectoryStep.name,
                DirectoryStep.directory_id,
                Directory.name.label("dir_name"),
                DirectoryStep.display_order,
                func.count(Opportunity.id).label("cnt"),
            )
            .join(Directory, Directory.id == DirectoryStep.directory_id)
            .outerjoin(
                Opportunity,
                (Opportunity.current_step_id == DirectoryStep.id)
                & (Opportunity.deleted_at.is_(None)),
            )
            .where(
                DirectoryStep.deleted_at.is_(None),  # type: ignore[union-attr]
                Directory.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .group_by(
                DirectoryStep.id,
                DirectoryStep.name,
                DirectoryStep.directory_id,
                Directory.name,
                DirectoryStep.display_order,
            )
            .order_by(DirectoryStep.directory_id, DirectoryStep.display_order)
        )).all()

        opportunities_by_step = [
            {
                "step_id": str(r[0]),
                "step_name": r[1],
                "directory_id": str(r[2]),
                "directory_name": r[3],
                "display_order": r[4],
                "count": r[5],
            }
            for r in step_rows
        ]

        # Conversion rates between consecutive steps (per directory)
        conversion_rates = self._compute_conversion_rates(opportunities_by_step)

        # Response outcomes
        _outcome_col = func.coalesce(Opportunity.response_outcome, "sin_respuesta").label("outcome")
        outcome_rows = (await self.session.execute(
            select(
                _outcome_col,
                func.count(Opportunity.id),
            ).where(not_deleted)
            .group_by(_outcome_col)
        )).all()
        response_outcomes = {r[0]: r[1] for r in outcome_rows}

        # By owner
        owner_rows = (await self.session.execute(
            select(
                User.id,
                User.display_name,
                func.count(Opportunity.id).label("cnt"),
            )
            .join(Opportunity, Opportunity.owner_user_id == User.id)
            .where(
                not_deleted,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .group_by(User.id, User.display_name)
            .order_by(func.count(Opportunity.id).desc())
        )).all()
        by_owner = [
            {"user_id": str(r[0]), "display_name": r[1], "count": r[2]}
            for r in owner_rows
        ]

        # Average time per step from activity_timeline
        avg_time_per_step = await self._calc_avg_time_per_step()

        return {
            "total_opportunities": total,
            "active_opportunities": active,
            "won_count": won_count,
            "lost_count": lost_count,
            "overall_win_rate": round(win_rate, 4),
            "opportunities_by_step": opportunities_by_step,
            "conversion_rates": conversion_rates,
            "won_lost": won_lost,
            "response_outcomes": response_outcomes,
            "by_owner": by_owner,
            "avg_time_per_step": avg_time_per_step,
        }

    @staticmethod
    def _compute_conversion_rates(steps_by_order: list[dict]) -> list[dict]:
        by_dir: dict[str, list[dict]] = defaultdict(list)
        for s in steps_by_order:
            by_dir[s["directory_id"]].append(s)

        rates: list[dict] = []
        for _dir_id, steps in by_dir.items():
            sorted_steps = sorted(steps, key=lambda x: x["display_order"])
            for i in range(len(sorted_steps) - 1):
                from_s = sorted_steps[i]
                to_s = sorted_steps[i + 1]
                from_count = from_s["count"]
                to_count = to_s["count"]
                rate = (to_count / from_count) if from_count > 0 else 0.0
                rates.append({
                    "from_step": from_s["step_name"],
                    "to_step": to_s["step_name"],
                    "from_count": from_count,
                    "to_count": to_count,
                    "rate": round(rate, 4),
                })
        return rates

    async def _calc_avg_time_per_step(self) -> list[dict]:
        rows = (await self.session.execute(
            select(Opportunity.activity_timeline).where(
                Opportunity.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )).scalars().all()

        step_durations: dict[str, list[float]] = defaultdict(list)
        for timeline in rows:
            if not isinstance(timeline, list) or len(timeline) < 2:
                continue
            for i in range(len(timeline) - 1):
                step = timeline[i].get("stage", "")
                at_str = timeline[i].get("at")
                next_at_str = timeline[i + 1].get("at")
                if not step or not at_str or not next_at_str:
                    continue
                try:
                    t0 = datetime.fromisoformat(at_str)
                    t1 = datetime.fromisoformat(next_at_str)
                    hours = (t1 - t0).total_seconds() / 3600
                    if hours > 0:
                        step_durations[step].append(hours)
                except (ValueError, TypeError):
                    continue

        return [
            {"step_name": k, "avg_hours": round(mean(v), 2)}
            for k, v in step_durations.items()
            if v
        ]

    # ── Activity metrics ──────────────────────────────────────────────

    async def get_activity_metrics(self) -> dict:
        # Search jobs by status
        sj_rows = (await self.session.execute(
            select(SearchJob.status, func.count(SearchJob.id))
            .group_by(SearchJob.status)
        )).all()
        search_jobs_by_status = {r[0]: r[1] for r in sj_rows}
        total_searches = sum(search_jobs_by_status.values())

        # Avg leads per search
        sub = (
            select(
                Lead.job_id,
                func.count(Lead.id).label("lc"),
            )
            .group_by(Lead.job_id)
            .subquery()
        )
        avg_leads_result = (await self.session.execute(
            select(func.coalesce(func.avg(sub.c.lc), 0))
        )).scalar_one()
        avg_leads_per_search = round(float(avg_leads_result), 2)

        # Avg lead score
        avg_score_result = (await self.session.execute(
            select(func.coalesce(func.avg(Lead.score), 0))
            .where(Lead.score.isnot(None))
        )).scalar_one()
        avg_lead_score = round(float(avg_score_result), 2)

        # Lead score distribution
        score_case = case(
            (Lead.score < 2, "0-2"),
            (Lead.score < 4, "2-4"),
            (Lead.score < 6, "4-6"),
            (Lead.score < 8, "6-8"),
            else_="8-10",
        )
        score_rows = (await self.session.execute(
            select(score_case.label("range"), func.count(Lead.id))
            .where(Lead.score.isnot(None))
            .group_by(score_case)
            .order_by(score_case)
        )).all()
        lead_score_distribution = [
            {"range": r[0], "count": r[1]} for r in score_rows
        ]

        # Validation rates
        val_rows = (await self.session.execute(
            select(Lead.validation_status, func.count(Lead.id))
            .group_by(Lead.validation_status)
        )).all()
        validation_rates = {r[0]: r[1] for r in val_rows}

        # Import source
        not_deleted = Opportunity.deleted_at.is_(None)  # type: ignore[union-attr]
        _src_col = func.coalesce(Opportunity.import_source, "desconocido").label("src")
        src_rows = (await self.session.execute(
            select(
                _src_col,
                func.count(Opportunity.id),
            ).where(not_deleted)
            .group_by(_src_col)
        )).all()
        by_import_source = {r[0]: r[1] for r in src_rows}

        # URL scrape jobs by status
        usj_rows = (await self.session.execute(
            select(UrlScrapeJob.status, func.count(UrlScrapeJob.id))
            .group_by(UrlScrapeJob.status)
        )).all()
        scrape_jobs_by_status = {r[0]: r[1] for r in usj_rows}

        # Top scraping sites
        site_rows = (await self.session.execute(
            select(
                ScrapingSite.title,
                func.count(UrlScrapeJob.id).label("job_count"),
            )
            .outerjoin(UrlScrapeJob, UrlScrapeJob.scraping_site_id == ScrapingSite.id)
            .group_by(ScrapingSite.id, ScrapingSite.title)
            .order_by(func.count(UrlScrapeJob.id).desc())
            .limit(10)
        )).all()
        top_scraping_sites = [
            {"name": r[0] or "Sin titulo", "count": r[1]} for r in site_rows
        ]

        # Contact coverage
        contact_coverage = await self._calc_contact_coverage()

        # Opportunities per day (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        thirty_days_ago = thirty_days_ago - timedelta(days=30)

        day_rows = (await self.session.execute(
            select(
                func.date(Opportunity.created_at).label("day"),
                func.count(Opportunity.id),
            )
            .where(not_deleted, Opportunity.created_at >= thirty_days_ago)
            .group_by(func.date(Opportunity.created_at))
            .order_by(func.date(Opportunity.created_at))
        )).all()
        opportunities_per_day = [
            {"date": str(r[0]), "count": r[1]} for r in day_rows
        ]

        # Top specialties / cities / countries from search_jobs
        top_specialties = await self._top_field(SearchJob.specialty, 10)
        top_cities = await self._top_field(SearchJob.city, 10)
        top_countries = await self._top_field(SearchJob.country, 10)

        # Active directories
        dir_rows = (await self.session.execute(
            select(
                Directory.name,
                func.count(Opportunity.id).label("cnt"),
            )
            .outerjoin(
                Opportunity,
                (Opportunity.directory_id == Directory.id)
                & (Opportunity.deleted_at.is_(None)),
            )
            .where(Directory.deleted_at.is_(None))  # type: ignore[union-attr]
            .group_by(Directory.id, Directory.name)
            .order_by(func.count(Opportunity.id).desc())
            .limit(10)
        )).all()
        active_directories = [
            {"name": r[0], "count": r[1]} for r in dir_rows
        ]

        return {
            "total_searches": total_searches,
            "avg_leads_per_search": avg_leads_per_search,
            "avg_lead_score": avg_lead_score,
            "search_jobs_by_status": search_jobs_by_status,
            "lead_score_distribution": lead_score_distribution,
            "validation_rates": validation_rates,
            "by_import_source": by_import_source,
            "scrape_jobs_by_status": scrape_jobs_by_status,
            "top_scraping_sites": top_scraping_sites,
            "contact_coverage": contact_coverage,
            "opportunities_per_day": opportunities_per_day,
            "top_specialties": top_specialties,
            "top_cities": top_cities,
            "top_countries": top_countries,
            "active_directories": active_directories,
        }

    async def _calc_contact_coverage(self) -> dict[str, float]:
        not_deleted = Opportunity.deleted_at.is_(None)  # type: ignore[union-attr]
        rows = (await self.session.execute(
            select(Opportunity.contacts).where(not_deleted)
        )).scalars().all()

        total = len(rows)
        if total == 0:
            return {"email": 0, "whatsapp": 0, "phone": 0, "linkedin": 0}

        counts: dict[str, int] = defaultdict(int)
        for contacts in rows:
            if not isinstance(contacts, list):
                continue
            types_found: set[str] = set()
            for c in contacts:
                if not isinstance(c, dict):
                    continue
                ctype = c.get("type") or c.get("kind") or ""
                val = c.get("value", "")
                if ctype and val:
                    types_found.add(ctype.lower())
            for t in types_found:
                counts[t] += 1

        return {
            k: round(v / total, 4) for k, v in counts.items()
        }

    async def _top_field(self, column, limit: int) -> list[dict]:
        rows = (await self.session.execute(
            select(column, func.count().label("cnt"))
            .where(column.isnot(None), column != "")
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        )).all()
        return [{"name": r[0], "count": r[1]} for r in rows]
