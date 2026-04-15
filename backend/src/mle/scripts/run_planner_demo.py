import asyncio
import json
import logging
from uuid import uuid4

from mle.logging_config import configure_logging
from mle.nodes.planner_node import planner_node
from mle.state.graph_state import LeadSearchGraphState


async def run() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    sample_state = LeadSearchGraphState(
        job_id=uuid4(),
        query_text="Cardiologos con email y linkedin en Tegucigalpa",
    )
    state_patch = await planner_node(sample_state)
    logger.info("Resultado planner demo:\n%s", json.dumps(state_patch, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())

