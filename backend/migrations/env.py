from alembic import context

from app import models  # noqa: F401  (registers the tables)
from app.db import Base, get_engine

target_metadata = Base.metadata


def run_migrations() -> None:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
