"""RQ worker entry point: ``python -m app.worker``."""
from __future__ import annotations

import logging

from redis import Redis
from rq import Queue, Worker

from app.config import get_settings

logging.basicConfig(level=logging.INFO)


def main() -> None:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue("solver", connection=connection)
    logging.info("Solver worker listening on queue 'solver'")
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
