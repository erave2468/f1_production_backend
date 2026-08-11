from __future__ import annotations

import logging

from app.db import Base, check_database, engine, ensure_database_exists
# Importing models registers all tables with Base.metadata.
from app import models  # noqa: F401


log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("Ensuring database exists")
    ensure_database_exists()
    log.info("Checking RDS connection")
    check_database()
    log.info("Creating missing database tables/indexes")
    Base.metadata.create_all(bind=engine)
    log.info("Database schema is ready")


if __name__ == "__main__":
    main()
