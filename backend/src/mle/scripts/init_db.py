import asyncio
import logging

from mle.db.base import init_db
from mle.logging_config import configure_logging


async def run() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Iniciando creacion de tablas")
    await init_db()
    logger.info("Tablas creadas correctamente")


if __name__ == "__main__":
    asyncio.run(run())

