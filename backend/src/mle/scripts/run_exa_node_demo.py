import asyncio
import json
import logging
from uuid import uuid4

from mle.logging_config import configure_logging
from mle.nodes.exa_webset_node import exa_webset_node
from mle.state.graph_state import LeadSearchGraphState


async def run() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    sample_state = LeadSearchGraphState(
        job_id=uuid4(),
        query_text="Cardiologos con email y linkedin en Tegucigalpa",
        planner_output={
            "search_config": {
                "query": "Cardiologos con email y linkedin en Tegucigalpa en Honduras",
                "type": "deep",
                "num_results": 10,
                "use_highlights": True,
            }
        },
        status="running",
        current_stage="exa_webset",
        progress=20,
    )
    state_patch = await exa_webset_node(sample_state)
    logger.info("Resultado exa node demo:\n%s", json.dumps(state_patch, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())

