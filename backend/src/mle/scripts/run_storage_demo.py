import asyncio
import json
import logging
from uuid import uuid4

from mle.logging_config import configure_logging
from mle.nodes.storage_export_node import storage_export_node
from mle.state.graph_state import LeadSearchGraphState


async def run() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    sample_state = LeadSearchGraphState(
        job_id=uuid4(),
        query_text="Cardiologos en Honduras",
        status="completed",
        current_stage="storage_export",
        progress=90,
        leads=[
            {
                "full_name": "Dra. Ana Perez",
                "specialty": "Cardiologia",
                "country": "Honduras",
                "city": "Tegucigalpa",
                "score": 8.8,
                "score_reasoning": "Perfil con contactos claros y fuentes verificables.",
                "email": "ana@example.com",
                "whatsapp": "+50499999999",
                "linkedin_url": "https://linkedin.com/in/ana",
                "source_citations": [
                    {"url": "https://example.com/ana", "title": "Perfil", "confidence": "high"}
                ],
            }
        ],
    )
    state_patch = await storage_export_node(sample_state)
    logger.info("Resultado storage demo:\n%s", json.dumps(state_patch, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())

