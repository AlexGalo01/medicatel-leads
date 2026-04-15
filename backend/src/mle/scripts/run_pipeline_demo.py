import asyncio
import json
import logging
from uuid import uuid4

from mle.logging_config import configure_logging
from mle.orchestration.pipeline import run_lead_pipeline
from mle.state.graph_state import LeadSearchGraphState


async def run() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    sample_state = LeadSearchGraphState(
        job_id=uuid4(),
        query_text="Cardiologos con email, whatsapp y linkedin en Tegucigalpa",
    )
    final_state = await run_lead_pipeline(sample_state)
    logger.info(
        "Pipeline finalizado:\n%s",
        json.dumps(
            {
                "status": final_state.status,
                "current_stage": final_state.current_stage,
                "progress": final_state.progress,
                "leads_count": len(final_state.leads),
                "errors": final_state.errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    asyncio.run(run())

