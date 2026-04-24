from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("EXA_API_KEY", "x")
os.environ.setdefault("GOOGLE_API_KEY", "x")
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from mle.api.routes import clarify_search_job, create_search_job
from mle.api.schemas import ClarifySearchJobRequest, SearchJobCreateRequest
from mle.db.models import User


class _FakeSessionCM:
    async def __aenter__(self) -> MagicMock:
        return MagicMock()

    async def __aexit__(self, *args: object) -> None:
        return None


class SearchJobClarifyFlowTests(unittest.TestCase):
    def test_create_defers_pipeline_when_clarifying(self) -> None:
        async def run() -> None:
            plan: dict = {
                "entity_type": "",
                "geo": {"country": "", "city": ""},
                "main_query": "doctors",
                "additional_queries": [],
                "required_channels": ["email"],
                "negative_constraints": "",
                "clarifying_question": "¿País?",
                "exa_category": None,
            }
            jid = uuid4()
            created = MagicMock()
            created.id = jid
            created.status = "pending"
            created.created_at = datetime.now(timezone.utc)

            pipeline_coros: list = []

            def capture_create_task(coro):  # type: ignore[no-untyped-def]
                pipeline_coros.append(coro)
                coro.close()
                m = MagicMock()
                m.cancel = MagicMock()
                return m

            fake_user = MagicMock(spec=User)
            payload = SearchJobCreateRequest(
                query="doctors in pharma",
                directory_id=uuid4(),
                contact_channels=["email"],
            )

            with patch("mle.api.routes.asyncio.create_task", side_effect=capture_create_task):
                with patch("mle.api.routes.async_session_factory", return_value=_FakeSessionCM()):
                    with patch(
                        "mle.api.routes.expand_user_search_query",
                        new_callable=AsyncMock,
                        return_value=("expanded text", {"focus": "general"}, plan),
                    ):
                        with patch("mle.api.routes.DirectoriesRepository") as DR:
                            DR.return_value.get = AsyncMock(return_value=MagicMock())
                            with patch("mle.api.routes.JobsRepository") as JR:
                                JR.return_value.create = AsyncMock(return_value=created)
                                out = await create_search_job(payload, fake_user)

            self.assertTrue(out.requires_clarification)
            self.assertEqual(out.clarifying_question, "¿País?")
            self.assertEqual(len(pipeline_coros), 0)

        asyncio.run(run())

    def test_create_starts_pipeline_without_clarifying(self) -> None:
        async def run() -> None:
            plan: dict = {
                "entity_type": "",
                "geo": {"country": "", "city": ""},
                "main_query": "doctors",
                "additional_queries": [],
                "required_channels": ["email"],
                "negative_constraints": "",
                "clarifying_question": None,
                "exa_category": None,
            }
            jid = uuid4()
            created = MagicMock()
            created.id = jid
            created.status = "pending"
            created.created_at = datetime.now(timezone.utc)

            pipeline_coros: list = []

            def capture_create_task(coro):  # type: ignore[no-untyped-def]
                pipeline_coros.append(coro)
                coro.close()
                m = MagicMock()
                m.cancel = MagicMock()
                return m

            fake_user = MagicMock(spec=User)
            payload = SearchJobCreateRequest(
                query="doctors in pharma",
                directory_id=uuid4(),
                contact_channels=["email"],
            )

            with patch("mle.api.routes.asyncio.create_task", side_effect=capture_create_task):
                with patch("mle.api.routes.async_session_factory", return_value=_FakeSessionCM()):
                    with patch(
                        "mle.api.routes.expand_user_search_query",
                        new_callable=AsyncMock,
                        return_value=("expanded text", {"focus": "general"}, plan),
                    ):
                        with patch("mle.api.routes.DirectoriesRepository") as DR:
                            DR.return_value.get = AsyncMock(return_value=MagicMock())
                            with patch("mle.api.routes.JobsRepository") as JR:
                                JR.return_value.create = AsyncMock(return_value=created)
                                out = await create_search_job(payload, fake_user)

            self.assertFalse(out.requires_clarification)
            self.assertEqual(len(pipeline_coros), 1)

        asyncio.run(run())

    def test_clarify_updates_and_starts_pipeline(self) -> None:
        async def run() -> None:
            job_id = uuid4()
            job = MagicMock()
            job.status = "pending"
            job.notes = None
            job.requested_contact_channels = ["email"]
            job.metadata_json = {
                "awaiting_clarification": True,
                "user_query": "empleados Farmafacil",
                "query_expansion_metadata": {"focus": "general"},
            }

            updated = MagicMock()
            updated.status = "pending"

            pipeline_coros: list = []

            def capture_create_task(coro):  # type: ignore[no-untyped-def]
                pipeline_coros.append(coro)
                coro.close()
                m = MagicMock()
                m.cancel = MagicMock()
                return m

            new_plan: dict = {
                "entity_type": "",
                "geo": {"country": "", "city": ""},
                "main_query": "empleados Farmafacil El Salvador",
                "additional_queries": [],
                "required_channels": ["email"],
                "negative_constraints": "",
                "clarifying_question": None,
                "exa_category": None,
            }

            fake_user = MagicMock(spec=User)

            with patch("mle.api.routes.asyncio.create_task", side_effect=capture_create_task):
                with patch("mle.api.routes.async_session_factory", return_value=_FakeSessionCM()):
                    with patch(
                        "mle.api.routes.expand_user_search_query",
                        new_callable=AsyncMock,
                        return_value=(
                            "empleados Farmafacil El Salvador",
                            {"focus": "general"},
                            new_plan,
                        ),
                    ):
                        with patch("mle.api.routes.JobsRepository") as JR:
                            JR.return_value.get_by_id = AsyncMock(return_value=job)
                            JR.return_value.update_pending_job_after_clarify = AsyncMock(
                                return_value=updated
                            )
                            out = await clarify_search_job(
                                job_id,
                                ClarifySearchJobRequest(reply="El Salvador"),
                                fake_user,
                            )

            self.assertEqual(out.job_id, str(job_id))
            JR.return_value.update_pending_job_after_clarify.assert_awaited_once()
            self.assertEqual(len(pipeline_coros), 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
