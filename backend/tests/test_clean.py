"""Unit tests for the LLM cleaning service (services/clean.py).

All OpenAI calls are stubbed — these cost nothing and need no API key.

    .venv/bin/python tests/test_clean.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.clean as clean  # noqa: E402


class _FakeResp:
    def __init__(self, content):
        msg = type("M", (), {"content": content})
        self.choices = [type("C", (), {"message": msg})]


def _stub_client(fn):
    """Install a fake OpenAI client whose completion returns fn(input_text)."""
    class _Completions:
        @staticmethod
        def create(**kw):
            return _FakeResp(fn(kw["messages"][-1]["content"]))

    class _Chat:
        completions = _Completions()

    clean._client = type("Client", (), {"chat": _Chat()})()


def _restore():
    clean._client = None


# ------------------------------------------------------------------ llm_clean

def test_llm_clean_returns_cleaned_text():
    _stub_client(lambda t: t.replace("[12]", ""))
    try:
        assert clean.llm_clean("prose [12] here") == "prose  here"
    finally:
        _restore()


def test_llm_clean_falls_back_on_drift():
    _stub_client(lambda t: "X" * (len(t) * 5))
    try:
        src = "some real prose that should survive the runaway model output"
        assert clean.llm_clean(src) == src
    finally:
        _restore()


def test_llm_clean_falls_back_on_exception():
    class Boom:
        @property
        def chat(self):
            raise RuntimeError("api down")
    clean._client = Boom()
    try:
        src = "some real prose here that must survive an API failure intact"
        assert clean.llm_clean(src) == src
    finally:
        _restore()


# ----------------------------------------------------------------- clean_many

def test_clean_many_preserves_order():
    # Order is load-bearing: ingest_book assigns Segment.order by list index.
    # Marker must be low-drift or the 35% guardrail (correctly) rejects it.
    _stub_client(lambda t: t + ".")
    try:
        texts = [f"chunk-{i} " + "body text " * 10 for i in range(25)]
        out, fallbacks = clean.clean_many(texts)
        assert fallbacks == 0, fallbacks
        assert out == [t + "." for t in texts]
        # index must survive in position
        for i, res in enumerate(out):
            assert res.startswith(f"chunk-{i} "), (i, res[:20])
    finally:
        _restore()


def test_clean_many_counts_fallbacks():
    # Every 3rd chunk drifts wildly -> fallback; others clean fine.
    def fn(t):
        return "X" * (len(t) * 6) if "bad" in t else f"ok:{t}"
    _stub_client(fn)
    try:
        texts = [("bad chunk number %d" % i) if i % 3 == 0 else ("good chunk number %d" % i)
                 for i in range(9)]
        out, fallbacks = clean.clean_many(texts)
        assert fallbacks == 3, fallbacks
        for i, (src, res) in enumerate(zip(texts, out)):
            if i % 3 == 0:
                assert res == src          # fell back to input verbatim
            else:
                assert res == f"ok:{src}"
    finally:
        _restore()


def test_clean_many_empty():
    assert clean.clean_many([]) == ([], 0)


def test_opening_chunks_allowed_to_shrink_hard():
    # A title-page-heavy opening chunk legitimately loses most of its length;
    # the same shrink deep in the book means truncation and must fall back.
    _stub_client(lambda t: t[: int(len(t) * 0.4)])
    try:
        texts = ["front matter junk " * 30] * 5
        out, fallbacks = clean.clean_many(texts)
        # chunks 0-1 accept the 60% shrink; chunks 2+ reject it
        assert out[0] == texts[0][: int(len(texts[0]) * 0.4)].strip()
        assert out[1] == texts[1][: int(len(texts[1]) * 0.4)].strip()
        assert out[2] == texts[2] and out[4] == texts[4]
        assert fallbacks == 3, fallbacks
    finally:
        _restore()


def test_growth_still_capped_on_opening_chunks():
    _stub_client(lambda t: t * 2)  # runaway doubling
    try:
        texts = ["opening chunk " * 20, "second chunk " * 20]
        out, fallbacks = clean.clean_many(texts)
        assert out == texts and fallbacks == 2
    finally:
        _restore()


def test_clean_many_runs_in_parallel():
    # Prove the ThreadPoolExecutor actually overlaps the network-bound calls.
    orig = clean._clean_one
    clean._clean_one = lambda t, *a: (time.sleep(0.2) or (t, True))
    try:
        started = time.monotonic()
        out, fallbacks = clean.clean_many([f"t{i}" for i in range(16)], max_workers=8)
        elapsed = time.monotonic() - started
        assert len(out) == 16 and fallbacks == 0
        # sequential would be ~3.2s; 8 workers should land near ~0.4s
        assert elapsed < 1.5, f"took {elapsed:.2f}s — not parallel"
    finally:
        clean._clean_one = orig


def test_clean_many_respects_concurrency_arg():
    orig = clean._clean_one
    clean._clean_one = lambda t, *a: (time.sleep(0.2) or (t, True))
    try:
        started = time.monotonic()
        clean.clean_many([f"t{i}" for i in range(4)], max_workers=1)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.7, f"took {elapsed:.2f}s — expected serial with 1 worker"
    finally:
        clean._clean_one = orig


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
