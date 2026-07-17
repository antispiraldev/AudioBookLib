"""Unit tests for storage.archive_prefix (no network — stubbed R2 client).

    .venv/bin/python tests/test_storage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.storage as storage  # noqa: E402


class _FakeR2:
    """Minimal in-memory stand-in for the boto3 S3 client."""
    def __init__(self, keys):
        self.store = {k: b"x" for k in keys}

    def get_paginator(self, _op):
        store = self.store

        class _Pag:
            def paginate(self, Bucket, Prefix):
                contents = [{"Key": k} for k in sorted(store) if k.startswith(Prefix)]
                yield {"Contents": contents}
        return _Pag()

    def copy_object(self, Bucket, CopySource, Key):
        self.store[Key] = self.store[CopySource["Key"]]

    def delete_object(self, Bucket, Key):
        self.store.pop(Key, None)


def _install(keys):
    storage._client = _FakeR2(keys)
    os.environ.setdefault("R2_ACCOUNT_ID", "test")  # is_enabled() gate


def _restore():
    storage._client = None


def test_archive_moves_and_rewrites_keys():
    _install(["audio/13/0000.mp3", "audio/13/0001.mp3", "audio/13/0002.mp3"])
    try:
        moved = storage.archive_prefix("audio/13/", "audio-archive/13/T1/")
        assert moved == 3, moved
        store = storage._client.store
        # originals gone, archived copies present with the tail preserved
        assert not any(k.startswith("audio/13/") for k in store), store
        assert store.keys() >= {
            "audio-archive/13/T1/0000.mp3",
            "audio-archive/13/T1/0001.mp3",
            "audio-archive/13/T1/0002.mp3",
        }, store
    finally:
        _restore()


def test_archive_leaves_other_books_untouched():
    _install(["audio/13/0000.mp3", "audio/14/0000.mp3"])
    try:
        storage.archive_prefix("audio/13/", "audio-archive/13/T1/")
        store = storage._client.store
        assert "audio/14/0000.mp3" in store, store  # book 14 untouched
        assert "audio/13/0000.mp3" not in store, store
    finally:
        _restore()


def test_archive_empty_prefix_is_noop():
    _install(["audio/14/0000.mp3"])
    try:
        assert storage.archive_prefix("audio/13/", "audio-archive/13/T1/") == 0
    finally:
        _restore()


def test_archive_no_client_returns_zero():
    _restore()
    saved = os.environ.pop("R2_ACCOUNT_ID", None)
    try:
        assert storage.archive_prefix("audio/13/", "audio-archive/13/T1/") == 0
    finally:
        if saved is not None:
            os.environ["R2_ACCOUNT_ID"] = saved


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
