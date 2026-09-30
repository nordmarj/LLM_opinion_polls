"""Client and runner with a mocked transport: no network."""
import asyncio
import json

import httpx
import pytest

from survey import runner, storage
from survey.client import OpenRouter, build_body
from survey.config import load_config
from survey.prompts import Cell

CFG = load_config()
FAKE_KEY = "sk-or-test-not-a-real-key"
_real_sleep = asyncio.sleep


async def _no_sleep(_s):
    await _real_sleep(0)


def ok_payload(content="<answer>Many-worlds</answer> because.", cost=0.001):
    return {"id": "gen-123", "model": "anthropic/claude-opus-5.5", "provider": "Anthropic",
            "choices": [{"message": {"role": "assistant", "content": content, "reasoning": "thinking..."},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": cost}}


def test_build_body_provider_pinning_and_effort():
    m = CFG.models["claude-opus-5.5"]
    b = build_body(m, [{"role": "user", "content": "hi"}], "high")
    assert b["provider"] == {"require_parameters": True, "allow_fallbacks": False, "order": ["anthropic"]}
    assert b["reasoning"] == {"effort": "high"}
    assert "reasoning" not in build_body(m, [], "default")


def test_retry_then_success(monkeypatch):
    monkeypatch.setattr("survey.client.asyncio.sleep", _no_sleep)
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}})
        return httpx.Response(200, json=ok_payload())

    async def go():
        c = OpenRouter(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
        r = await c.chat({"model": "x"})
        await c.aclose()
        return r

    r = asyncio.run(go())
    assert r.ok and r.attempts == 3 and r.text.startswith("<answer>")
    assert calls[0].headers["authorization"] == f"Bearer {FAKE_KEY}"


def test_non_retryable_error_returns_immediately():
    def handler(req):
        return httpx.Response(400, json={"error": {"code": 400, "message": "bad param"}})

    async def go():
        c = OpenRouter(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
        r = await c.chat({"model": "x"})
        await c.aclose()
        return r

    r = asyncio.run(go())
    assert not r.ok and r.attempts == 1 and "bad param" in r.error


@pytest.fixture
def tmp_results(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PILOT_DIR", tmp_path / "pilot")
    monkeypatch.setattr(storage, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(runner, "PILOT_DIR", tmp_path / "pilot")
    monkeypatch.setattr(runner, "RAW_DIR", tmp_path / "raw")
    return tmp_path


def run(cells, n, handler, cap=None):
    cfg = load_config()
    if cap is not None:
        cfg.budget["hard_cap_usd"] = cap
    client = OpenRouter(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
    return asyncio.run(runner.run_cells(cfg, cells, n, run_id="t1", pilot=True,
                                        est_cost_per_sample={"claude-opus-5.5": 0.001}, client=client))


def test_runner_writes_records_and_resumes(tmp_results):
    cells = [Cell("qm_full", "none", "pick", "default", "claude-opus-5.5"),
             Cell("qm_binary", "lw_reader", "pick", "default", "claude-opus-5.5")]
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=ok_payload())

    rep = run(cells, 3, handler)
    assert rep["cells_short_of_n"] == {} and len(seen) == 6
    recs = list(storage.iter_records(tmp_results / "pilot"))
    assert len(recs) == 6
    r0 = next(r for r in recs if r["cell"]["question"] == "qm_full")
    assert r0["served_provider"] == "Anthropic" and r0["generation_id"] == "gen-123"
    assert r0["reasoning"] == "thinking..." and len(r0["option_order"]) == 9
    assert r0["request"]["provider"]["allow_fallbacks"] is False
    assert FAKE_KEY not in json.dumps(recs)
    # resume: nothing more to do
    run(cells, 3, handler)
    assert len(seen) == 6
    # top up to 4
    run(cells, 4, handler)
    assert len(seen) == 8


def test_runner_logs_failures_and_retries_in_later_pass(tmp_results, monkeypatch):
    monkeypatch.setattr("survey.client.asyncio.sleep", _no_sleep)
    cells = [Cell("qm_full", "none", "pick", "default", "claude-opus-5.5")]
    n_calls = {"n": 0}

    def handler(req):
        n_calls["n"] += 1
        if n_calls["n"] == 1:
            return httpx.Response(400, json={"error": {"code": 400, "message": "transient-looking 400"}})
        return httpx.Response(200, json=ok_payload())

    rep = run(cells, 2, handler)
    recs = list(storage.iter_records(tmp_results / "pilot"))
    assert sum(not r["ok"] for r in recs) == 1 and sum(r["ok"] for r in recs) == 2
    assert rep["cells_short_of_n"] == {} and list(rep["failed_attempts_per_cell"].values()) == [1]


def test_runner_stops_at_budget(tmp_results):
    cells = [Cell("qm_full", "none", "pick", "default", "claude-opus-5.5")]

    def handler(req):
        return httpx.Response(200, json=ok_payload(cost=0.001))

    rep = run(cells, 10, handler, cap=0.0035)
    recs = list(storage.iter_records(tmp_results / "pilot"))
    assert len(recs) < 10 and rep["stopped"]
