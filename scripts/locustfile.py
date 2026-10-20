"""Locust load test for ShopMate: health, product search, policy QA (SSE), orders, SSE fan-out.

Scope and honesty
-----------------
* Only local endpoints are hit: no third-party service is contacted.
* The answer model is not configured, so the "policy QA" scenario measures the **retrieval
  + gate** path (embedding + Milvus + PostgreSQL) and the SSE plumbing, not LLM latency.
  The report must not present these numbers as "policy answer latency".
* Rate limits are raised for the run (``RATE_LIMIT_CHAT_PER_MINUTE``) because the default
  20/min would turn the test into a 429 measurement. That deviation is recorded in the
  report; it is not the production configuration.
* Every virtual user logs in once (captcha is solved the same way the browser does) and
  reuses its token, so auth traffic is not the bottleneck being measured.

Run (after starting a local uvicorn on 18001)::

    uv run --with locust locust -f scripts/locustfile.py --headless \
        -u 20 -r 5 -t 60s --host http://127.0.0.1:18001 \
        --csv data/eval/results/locust-stage13 --only-summary
"""

from __future__ import annotations

import os
import re
import time
import uuid

import requests
from locust import HttpUser, between, task

EMAIL = os.environ.get("SHOPMATE_LOAD_EMAIL", "stage13.load@example.invalid")
PASSWORD = os.environ.get("SHOPMATE_LOAD_PASSWORD", "stage13-load-pass-1")
CAPTCHA_RE = re.compile(r"(\d+)\s*\+\s*(\d+)")

POLICY_QUESTIONS = (
    "七天无理由退货从什么时候开始计算？",
    "退款一般多久能到账？",
    "包邮门槛是多少？",
    "新加坡订单满多少包邮？",
)
PRODUCT_QUERIES = ("降噪耳机", "机械键盘", "无线鼠标", "充电器", "智能手表")


class ShopMateUser(HttpUser):
    """One shopper: login -> conversation -> weighted mix of read paths."""

    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        self.token: str | None = None
        self.conversation_id: str | None = None
        self._stream_session = requests.Session()
        self._authenticate()
        self._create_conversation()

    # -- setup -------------------------------------------------------------
    def _captcha(self) -> dict[str, str]:
        payload = self.client.get("/api/v1/auth/captcha", name="/api/v1/auth/captcha").json()
        data = payload["data"]
        match = CAPTCHA_RE.search(data["question"])
        assert match is not None, f"验证码格式异常: {data['question']}"
        answer = str(int(match.group(1)) + int(match.group(2)))
        return {"captcha_token": data["captcha_token"], "captcha_answer": answer}

    def _authenticate(self) -> None:
        challenge = self._captcha()
        body = {"email": EMAIL, "password": PASSWORD, **challenge}
        response = self.client.post("/api/v1/auth/login", json=body, name="/api/v1/auth/login")
        if response.status_code == 200:
            self.token = response.json()["data"]["access_token"]
            return
        # First run: create the load-test account. A 400 "duplicate" is expected when many
        # virtual users race to create the same account, so its result is deliberately ignored.
        self.client.post(
            "/api/v1/auth/register",
            json={"email": EMAIL, "password": PASSWORD, **self._captcha()},
            name="/api/v1/auth/register",
        )
        challenge = self._captcha()
        body = {"email": EMAIL, "password": PASSWORD, **challenge}
        response = self.client.post(
            "/api/v1/auth/login", json=body, name="/api/v1/auth/login"
        )
        if response.status_code != 200:
            response.failure(f"登录失败: HTTP {response.status_code}")
            return
        self.token = response.json()["data"]["access_token"]

    def _create_conversation(self) -> None:
        response = self.client.post(
            "/api/v1/conversations",
            json={"title": "阶段13压测"},
            headers=self._headers(),
            name="/api/v1/conversations [create]",
        )
        if response.status_code == 201:
            self.conversation_id = response.json()["data"]["id"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # -- scenarios ---------------------------------------------------------
    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")

    @task(4)
    def product_search(self) -> None:
        query = PRODUCT_QUERIES[uuid.uuid4().int % len(PRODUCT_QUERIES)]
        self.client.get(
            "/api/v1/products/search",
            params={"q": query, "limit": 10},
            headers=self._headers(),
            name="/api/v1/products/search",
        )

    @task(3)
    def order_query(self) -> None:
        self.client.get("/api/v1/orders", headers=self._headers(), name="/api/v1/orders")

    @task(3)
    def policy_qa_sse(self) -> None:
        self._stream(POLICY_QUESTIONS[uuid.uuid4().int % len(POLICY_QUESTIONS)], "chat-sse-policy")

    @task(1)
    def sse_fanout(self) -> None:
        """Product turn over SSE: cheap, deterministic, and keeps the stream open long enough."""
        self._stream("降噪耳机有什么推荐？", "chat-sse-product")

    # -- helper ------------------------------------------------------------
    def _stream(self, message: str, name: str) -> None:
        """Measure SSE explicitly: locust's own timer stops at response headers.

        A plain ``requests`` session is used for the stream so that the two numbers the
        report actually needs — first token and full stream — are measured, instead of the
        ~15 ms "headers received" figure a StreamingResponse returns.
        """
        if not self.conversation_id:
            return
        payload = {
            "conversation_id": self.conversation_id,
            "message": message,
            "client_message_id": str(uuid.uuid4()),
        }
        started = time.perf_counter()
        first_token: float | None = None
        events = 0
        error: str | None = None
        try:
            response = self._stream_session.post(
                f"{self.host}/api/v1/chat/stream",
                json=payload,
                headers=self._headers(),
                stream=True,
                timeout=60,
            )
            if response.status_code != 200:
                error = f"HTTP {response.status_code}"
            else:
                for raw in response.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode() if isinstance(raw, bytes) else raw
                    if line.startswith("event:"):
                        events += 1
                        if first_token is None:
                            first_token = (time.perf_counter() - started) * 1000
                    if line.startswith("event: done"):
                        break
                if events == 0:
                    error = "SSE 未收到任何事件"
        except Exception as exc:  # noqa: BLE001 - reported as a locust failure
            error = f"{type(exc).__name__}: {exc}"
        total = (time.perf_counter() - started) * 1000
        self.environment.events.request.fire(
            request_type="SSE",
            name=f"/api/v1/chat/stream [{name}] first-token",
            response_time=first_token if first_token is not None else total,
            response_length=0,
            exception=Exception(error) if error else None,
        )
        self.environment.events.request.fire(
            request_type="SSE",
            name=f"/api/v1/chat/stream [{name}] full",
            response_time=total,
            response_length=events,
            exception=Exception(error) if error else None,
        )


