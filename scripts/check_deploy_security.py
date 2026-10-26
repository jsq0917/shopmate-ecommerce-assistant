"""Static deployment security review (stage 14).

This is a *static* checker: it reads the deployment artefacts in the repository and reports
whether the production hardening rules in AGENTS.md §14.3/§14.5 still hold. It does not talk
to Docker, so it runs in CI and on a fresh clone without any daemon.

Usage::

    uv run python scripts/check_deploy_security.py
    uv run python scripts/check_deploy_security.py --json
    uv run python scripts/check_deploy_security.py --strict   # WARN also fails

Exit code: 0 when every check passes, 1 when any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROD_COMPOSE = PROJECT_ROOT / "compose.prod.yaml"
DEV_COMPOSE = PROJECT_ROOT / "compose.yaml"
API_DOCKERFILE = PROJECT_ROOT / "Dockerfile"
WEB_DOCKERFILE_PROD = PROJECT_ROOT / "web" / "Dockerfile.prod"
ENV_EXAMPLES = (PROJECT_ROOT / ".env.example", PROJECT_ROOT / ".env.prod.example")

LONG_RUNNING_SERVICES = ("postgres", "redis", "etcd", "minio", "milvus", "api", "web")
DATA_SERVICES = ("postgres", "redis", "etcd", "minio", "milvus")

# 中国大陆手机号、18 位身份证号、银行卡号（13-19 位连续数字）。
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "手机号": re.compile(r"(?<![\d.])1[3-9]\d{9}(?![\d.])"),
    "身份证号": re.compile(
        r"(?<![\d.])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
        r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\d.])"
    ),
    "银行卡号": re.compile(r"(?<![\d.])\d{16,19}(?![\d.])"),
}
PII_SCAN_PATHS = ("data", "docs", "README.md", ".env.example", ".env.prod.example")
PII_SUFFIXES = {".md", ".json", ".jsonl", ".csv", ".txt", ".yaml", ".example"}


@dataclass(frozen=True)
class Finding:
    """One check result."""

    check: str
    status: str
    detail: str


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _services(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = config.get("services") or {}
    return {name: (body or {}) for name, body in services.items() if isinstance(body, dict)}


def _ok(check: str, passed: bool, good: str, bad: str) -> Finding:
    """Build a PASS/FAIL finding with the matching detail text."""
    return Finding(check, "PASS" if passed else "FAIL", good if passed else bad)


def check_compose_privileges() -> list[Finding]:
    """Reject privileged mode, host networking and Docker socket mounts."""
    findings: list[Finding] = []
    for path in (PROD_COMPOSE, DEV_COMPOSE):
        if not path.exists():
            findings.append(Finding(f"{_rel(path)} 存在", "FAIL", "缺少编排文件"))
            continue
        label = _rel(path)
        services = _services(_load_yaml(path))
        privileged = [n for n, s in services.items() if s.get("privileged") is True]
        host_net = [n for n, s in services.items() if s.get("network_mode") == "host"]
        sockets = [
            n
            for n, s in services.items()
            if any("docker.sock" in str(v) for v in (s.get("volumes") or []))
        ]
        findings.append(
            _ok(
                f"{label}: 无 privileged",
                not privileged,
                "全部服务均未开启 privileged",
                f"privileged=true：{', '.join(privileged)}",
            )
        )
        findings.append(
            _ok(
                f"{label}: 无 host 网络",
                not host_net,
                "未使用 host 网络",
                f"network_mode=host：{', '.join(host_net)}",
            )
        )
        findings.append(
            _ok(
                f"{label}: 无 Docker socket 挂载",
                not sockets,
                "未挂载 /var/run/docker.sock",
                f"挂载 docker.sock：{', '.join(sockets)}",
            )
        )
    return findings


def check_prod_hardening() -> list[Finding]:
    """Verify read-only root, capability drop, resource limits and log rotation."""
    findings: list[Finding] = []
    services = _services(_load_yaml(PROD_COMPOSE))

    for name in ("api", "web"):
        body = services.get(name, {})
        read_only = body.get("read_only") is True
        cap_drop = [str(value).upper() for value in (body.get("cap_drop") or [])]
        no_new_privs = any(
            "no-new-privileges" in str(opt) for opt in (body.get("security_opt") or [])
        )
        tmpfs = body.get("tmpfs") or []
        findings.append(
            _ok(
                f"compose.prod.yaml/{name}: 只读根文件系统",
                read_only and bool(tmpfs),
                "read_only=true 且有 tmpfs 可写目录",
                "缺少 read_only: true 或 tmpfs",
            )
        )
        findings.append(
            _ok(
                f"compose.prod.yaml/{name}: 丢弃能力",
                "ALL" in cap_drop,
                "cap_drop: ALL",
                "cap_drop 未包含 ALL",
            )
        )
        findings.append(
            _ok(
                f"compose.prod.yaml/{name}: no-new-privileges",
                no_new_privs,
                "security_opt 已设置",
                "缺少 security_opt: no-new-privileges:true",
            )
        )

    for name in LONG_RUNNING_SERVICES:
        body = services.get(name, {})
        options = (body.get("logging") or {}).get("options") or {}
        rotated = bool(options.get("max-size") and options.get("max-file"))
        findings.append(
            _ok(
                f"compose.prod.yaml/{name}: 日志轮转",
                rotated,
                f"max-size={options.get('max-size')}, max-file={options.get('max-file')}",
                "缺少 json-file 的 max-size / max-file",
            )
        )

    for name in LONG_RUNNING_SERVICES:
        body = services.get(name, {})
        limits = ((body.get("deploy") or {}).get("resources") or {}).get("limits") or {}
        ok = bool(limits.get("cpus") and limits.get("memory"))
        findings.append(
            _ok(
                f"compose.prod.yaml/{name}: 资源限制",
                ok,
                f"cpus={limits.get('cpus')}, memory={limits.get('memory')}",
                "缺少 deploy.resources.limits 的 cpus / memory",
            )
        )

    exposed = [name for name in DATA_SERVICES if services.get(name, {}).get("ports")]
    findings.append(
        _ok(
            "compose.prod.yaml: 数据服务不暴露宿主端口",
            not exposed,
            "PostgreSQL/Redis/etcd/MinIO/Milvus 仅在内部网络",
            f"仍映射端口：{', '.join(exposed)}",
        )
    )

    api_ports = services.get("api", {}).get("ports") or []
    findings.append(
        _ok(
            "compose.prod.yaml: API 不直接对外",
            not api_ports,
            "仅 web 暴露端口，API 经反代访问",
            f"api 映射了 {api_ports}",
        )
    )
    return findings


def check_images() -> list[Finding]:
    """Reject floating ``latest`` tags and unresolved image references."""
    findings: list[Finding] = []
    services = _services(_load_yaml(PROD_COMPOSE))
    floating: list[str] = []
    pinned = 0
    interpolated = 0

    for name, body in services.items():
        image = str(body.get("image") or "")
        if not image:
            floating.append(f"{name}(缺失 image)")
            continue
        if "${" in image:
            interpolated += 1
            continue
        last = image.rsplit("/", 1)[-1]
        if image.endswith(":latest") or ":" not in last:
            floating.append(f"{name}={image}")
        else:
            pinned += 1

    example_values: dict[str, str] = {}
    env_prod = PROJECT_ROOT / ".env.prod.example"
    if env_prod.exists():
        for line in env_prod.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            example_values[key.strip()] = value.strip()

    for key in ("API_IMAGE", "WEB_IMAGE"):
        value = example_values.get(key, "")
        if not value:
            floating.append(f"{key}(未在 .env.prod.example 中给出)")
        elif value.endswith(":latest") or ":" not in value.rsplit("/", 1)[-1]:
            floating.append(f"{key}={value}")
        else:
            pinned += 1

    findings.append(
        _ok(
            "镜像固定（无 latest / 无浮动 tag）",
            not floating,
            f"固定镜像 {pinned} 个，引用变量 {interpolated} 个",
            "；".join(floating),
        )
    )

    dockerfile_issues: list[str] = []
    for path, expected_user in ((API_DOCKERFILE, "10001"), (WEB_DOCKERFILE_PROD, "nginx")):
        text = path.read_text(encoding="utf-8")
        if f"USER {expected_user}" not in text:
            dockerfile_issues.append(f"{_rel(path)} 缺少 USER {expected_user}")
        if "--reload" in text:
            dockerfile_issues.append(f"{_rel(path)} 启用了 --reload")
    findings.append(
        _ok(
            "Dockerfile: 非 root 且关闭 reload",
            not dockerfile_issues,
            "api 使用 UID 10001，web 使用 nginx 用户，均无 --reload",
            "；".join(dockerfile_issues),
        )
    )
    return findings


def check_secrets() -> list[Finding]:
    """Ensure no plaintext credential is committed and no ``.env`` is tracked."""
    findings: list[Finding] = []
    placeholder_markers = ("replace-with", "change-me", "example.invalid", "your-", "xxxx")

    problems: list[str] = []
    for path in ENV_EXAMPLES:
        if not path.exists():
            problems.append(f"缺少 {_rel(path)}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key, value = key.strip(), value.strip()
            if not value:
                continue
            sensitive = key.upper().endswith(("PASSWORD", "SECRET", "API_KEY", "TOKEN"))
            looks_fake = any(marker in value.lower() for marker in placeholder_markers)
            if sensitive and not looks_fake:
                problems.append(f"{_rel(path)}:{key} 不是占位符")
    findings.append(
        _ok(
            "环境变量样例只含占位符",
            not problems,
            ".env.example / .env.prod.example 的敏感键均为占位符",
            "；".join(problems),
        )
    )

    try:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        tracked_lines = [line for line in tracked.stdout.splitlines() if line.strip()]
        leaked = [
            name
            for name in tracked_lines
            if Path(name).name in {".env", ".env.prod", ".env.local"}
            or (name.startswith(".env.") and not name.endswith(".example"))
        ]
        findings.append(
            _ok(
                "git 未跟踪真实 .env",
                not leaked,
                "git 索引中没有任何 .env / .env.prod",
                f"已跟踪的密钥文件：{', '.join(leaked)}",
            )
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - git optional
        findings.append(Finding("git 未跟踪真实 .env", "WARN", f"无法执行 git ls-files：{exc}"))

    literal: list[str] = []
    for name, body in _services(_load_yaml(PROD_COMPOSE)).items():
        environment = body.get("environment") or {}
        pairs: list[tuple[str, str]] = []
        if isinstance(environment, dict):
            pairs = [(str(k), str(v)) for k, v in environment.items()]
        elif isinstance(environment, list):
            for entry in environment:
                key, _, value = str(entry).partition("=")
                pairs.append((key, value))
        for key, value in pairs:
            sensitive = key.upper().endswith(("PASSWORD", "SECRET", "API_KEY", "TOKEN"))
            if sensitive and "${" not in value and value:
                literal.append(f"{name}.{key}")
    findings.append(
        _ok(
            "compose.prod.yaml 不内联口令",
            not literal,
            "口令全部来自 ${...:?} 强制注入",
            f"内联敏感值：{', '.join(literal)}",
        )
    )
    return findings


def check_pii() -> list[Finding]:
    """Scan data/docs/env samples for real-looking PII (tests are excluded by design)."""
    hits: list[str] = []
    scanned = 0

    for rel in PII_SCAN_PATHS:
        target = PROJECT_ROOT / rel
        if not target.exists():
            continue
        if target.is_file():
            files = [target]
        else:
            files = [
                path
                for path in target.rglob("*")
                if path.is_file() and path.suffix.lower() in PII_SUFFIXES
            ]
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1
            for label, pattern in PII_PATTERNS.items():
                for match in pattern.finditer(text):
                    hits.append(f"{_rel(path)}:{label}:{match.group(0)[:4]}***")

    if hits:
        detail = f"{len(hits)} 处疑似命中：{'; '.join(hits[:5])}"
        return [Finding("数据/文档中无真实 PII", "WARN", detail)]
    return [
        Finding(
            "数据/文档中无真实 PII",
            "PASS",
            f"扫描 {scanned} 个文件，未命中手机号/身份证/银行卡模式",
        )
    ]


def run_checks() -> list[Finding]:
    """Run every check group."""
    findings: list[Finding] = []
    findings.extend(check_compose_privileges())
    findings.extend(check_prod_hardening())
    findings.extend(check_images())
    findings.extend(check_secrets())
    findings.extend(check_pii())
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="ShopMate 生产部署静态安全复查")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    args = parser.parse_args()

    findings = run_checks()
    failures = [f for f in findings if f.status == "FAIL"]
    warnings = [f for f in findings if f.status == "WARN"]

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [asdict(finding) for finding in findings],
                    "failed": len(failures),
                    "warned": len(warnings),
                    "passed": len(findings) - len(failures) - len(warnings),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        width = max(len(finding.check) for finding in findings)
        for finding in findings:
            print(f"[{finding.status:<4}] {finding.check:<{width}}  {finding.detail}")
        print()
        passed = len(findings) - len(failures) - len(warnings)
        print(
            f"合计 {len(findings)} 项：PASS {passed} / WARN {len(warnings)} / FAIL {len(failures)}"
        )
        if warnings:
            print("WARN 项需要人工确认，不自动视为通过。")

    if failures or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
