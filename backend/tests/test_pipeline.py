from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if "langsmith" not in sys.modules:

    def _traceable_stub(**_kwargs):  # noqa: ANN003
        def _decorator(fn):  # noqa: ANN001
            return fn

        return _decorator

    _ls = types.ModuleType("langsmith")
    _ls.traceable = _traceable_stub  # type: ignore[attr-defined]
    sys.modules["langsmith"] = _ls

from mle.orchestration import pipeline as pipeline_module
from mle.state.graph_state import LeadSearchGraphState


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_success_path(self) -> None:
        async def fake_planner_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "running",
                "current_stage": "exa_webset",
                "progress": 20,
                "planner_output": {"search_config": {"query": "query de prueba"}},
            }

        async def fake_exa_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "running",
                "current_stage": "relevance_filter",
                "progress": 68,
                "exa_raw_results": [{"title": "Dra. Test", "url": "https://linkedin.com/in/test"}],
            }

        async def fake_relevance_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "running",
                "current_stage": "search_finalize",
                "progress": 72,
                "exa_raw_results": list(state.exa_raw_results),
                "langsmith_metadata": {
                    **state.langsmith_metadata,
                    "relevance_filter_kept": len(state.exa_raw_results),
                    "relevance_filter_dropped": 0,
                    "relevance_filter_mode": "test_bypass",
                },
            }

        async def fake_finalize_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "completed",
                "current_stage": "done",
                "progress": 100,
                "langsmith_metadata": {
                    **state.langsmith_metadata,
                    "pipeline_mode": "presearch_and_search_only",
                    "exa_results_preview": [
                        {"index": 1, "title": "Dra. Test", "url": "https://linkedin.com/in/test", "snippet": None}
                    ],
                },
            }

        original_planner = pipeline_module.planner_node
        original_exa = pipeline_module.exa_webset_node
        original_relevance = pipeline_module.relevance_filter_node
        original_finalize = pipeline_module.search_finalize_node
        pipeline_module.planner_node = fake_planner_node
        pipeline_module.exa_webset_node = fake_exa_node
        pipeline_module.relevance_filter_node = fake_relevance_node
        pipeline_module.search_finalize_node = fake_finalize_node

        try:
            initial_state = LeadSearchGraphState(
                job_id=uuid4(),
                query_text="Cardiologos en Honduras",
            )
            with patch.object(pipeline_module, "persist_pipeline_progress", new_callable=AsyncMock):
                final_state = await pipeline_module.run_lead_pipeline(initial_state)

            self.assertEqual(final_state.status, "completed")
            self.assertEqual(final_state.current_stage, "done")
            self.assertEqual(final_state.progress, 100)
            self.assertEqual(len(final_state.exa_raw_results), 1)
        finally:
            pipeline_module.planner_node = original_planner
            pipeline_module.exa_webset_node = original_exa
            pipeline_module.relevance_filter_node = original_relevance
            pipeline_module.search_finalize_node = original_finalize

    async def test_pipeline_stops_on_planner_error(self) -> None:
        async def fake_planner_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "error",
                "current_stage": "planner",
                "progress": state.progress,
                "errors": ["Planner fallo de prueba"],
            }

        original_planner = pipeline_module.planner_node
        pipeline_module.planner_node = fake_planner_node
        try:
            initial_state = LeadSearchGraphState(
                job_id=uuid4(),
                query_text="Cardiologos en Honduras",
            )
            with patch.object(pipeline_module, "persist_pipeline_progress", new_callable=AsyncMock):
                final_state = await pipeline_module.run_lead_pipeline(initial_state)
            self.assertEqual(final_state.status, "error")
            self.assertEqual(final_state.current_stage, "planner")
            self.assertIn("Planner fallo de prueba", final_state.errors)
        finally:
            pipeline_module.planner_node = original_planner


if __name__ == "__main__":
    unittest.main()
