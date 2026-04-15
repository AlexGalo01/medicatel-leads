from __future__ import annotations

import unittest
from uuid import uuid4

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
                "current_stage": "scoring_cleaning",
                "progress": 60,
                "exa_raw_results": [{"title": "Dra. Test", "url": "https://linkedin.com/in/test"}],
            }

        async def fake_scoring_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "completed",
                "current_stage": "storage_export",
                "progress": 90,
                "leads": [{"full_name": "Dra. Test", "score": 8.5}],
            }

        async def fake_storage_node(state: LeadSearchGraphState) -> dict[str, object]:
            return {
                "status": "completed",
                "current_stage": "done",
                "progress": 100,
                "langsmith_metadata": {"export_path": "backend/exports/leads_test.csv"},
            }

        original_planner = pipeline_module.planner_node
        original_exa = pipeline_module.exa_webset_node
        original_scoring = pipeline_module.scoring_cleaning_node
        original_storage = pipeline_module.storage_export_node
        pipeline_module.planner_node = fake_planner_node
        pipeline_module.exa_webset_node = fake_exa_node
        pipeline_module.scoring_cleaning_node = fake_scoring_node
        pipeline_module.storage_export_node = fake_storage_node

        try:
            initial_state = LeadSearchGraphState(
                job_id=uuid4(),
                query_text="Cardiologos en Honduras",
            )
            final_state = await pipeline_module.run_lead_pipeline(initial_state)

            self.assertEqual(final_state.status, "completed")
            self.assertEqual(final_state.current_stage, "done")
            self.assertEqual(final_state.progress, 100)
            self.assertEqual(len(final_state.leads), 1)
        finally:
            pipeline_module.planner_node = original_planner
            pipeline_module.exa_webset_node = original_exa
            pipeline_module.scoring_cleaning_node = original_scoring
            pipeline_module.storage_export_node = original_storage

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
            final_state = await pipeline_module.run_lead_pipeline(initial_state)
            self.assertEqual(final_state.status, "error")
            self.assertEqual(final_state.current_stage, "planner")
            self.assertIn("Planner fallo de prueba", final_state.errors)
        finally:
            pipeline_module.planner_node = original_planner


if __name__ == "__main__":
    unittest.main()

