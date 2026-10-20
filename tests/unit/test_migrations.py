"""Alembic migration-chain smoke tests that do not require PostgreSQL."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_a_single_baseline_head() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20261019_0004"]
