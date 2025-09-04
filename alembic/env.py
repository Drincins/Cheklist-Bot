from dotenv import load_dotenv
load_dotenv()

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# --- Alembic config (alembic.ini) ---
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Импорт Base и МОДЕЛЕЙ (чтобы Base.metadata видела все таблицы) ---
from checklist.db.base import Base
# Важно: импортировать модели ДО назначения target_metadata
from checklist.db.models import (
    User, Role, Company, Department, Position,
    Checklist, ChecklistQuestion, ChecklistAnswer, ChecklistQuestionAnswer
)

# Метадата для автогенерации
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,   # безопасно и для PostgreSQL
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode'."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    # Пробрасываем строку подключения из .env в alembic.ini
    config.set_main_option("sqlalchemy.url", db_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
