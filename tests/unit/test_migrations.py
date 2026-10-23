"""Alembic migration-chain smoke tests that do not require PostgreSQL."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_a_single_baseline_head() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    script = ScriptDirectory.from_config(config)

    # 阶段 18 新增 20261023_0008（会话级知识库选择），阶段 19 新增 20261023_0009
    # （会话级推理参数）；仍要求单头，避免分支迁移。
    assert script.get_heads() == ["20261023_0009"]
