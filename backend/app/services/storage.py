import os
import tempfile
from contextlib import contextmanager

import boto3
from botocore.config import Config

_client = None


def _get_client():
    global _client
    if _client is None:
        account_id = os.getenv("R2_ACCOUNT_ID")
        if not account_id:
            return None
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def _bucket() -> str:
    return os.getenv("R2_BUCKET_NAME", "audiobooklib")


def is_enabled() -> bool:
    return bool(os.getenv("R2_ACCOUNT_ID"))


def upload(local_path: str, key: str) -> None:
    client = _get_client()
    if client:
        client.upload_file(local_path, _bucket(), key)


def download(key: str, local_path: str) -> None:
    client = _get_client()
    if not client:
        raise RuntimeError("R2 not configured")
    client.download_file(_bucket(), key, local_path)


def is_r2_key(path: str) -> bool:
    """R2 keys have no storage/ prefix — local paths always do."""
    return is_enabled() and not path.startswith("storage/")


def pdf_available(path: str) -> bool:
    """True if the source PDF can actually be fetched for (re)processing.

    Migrated books carry local storage/ paths whose files no longer exist in
    the container and were never pushed to R2 — reprocessing those needs a
    fresh upload, so callers check this before wiping segments.
    """
    if is_r2_key(path):
        client = _get_client()
        if not client:
            return False
        try:
            client.head_object(Bucket=_bucket(), Key=path)
            return True
        except Exception:
            return False
    return os.path.exists(path)


@contextmanager
def local_pdf(path: str):
    """Yield a readable local path for a pdf_path that may be an R2 key."""
    if not is_r2_key(path):
        yield path
        return
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        download(path, tmp.name)
        yield tmp.name
    finally:
        os.remove(tmp.name)


def presigned_url(key: str, expiry: int = 3600) -> str:
    client = _get_client()
    if not client:
        raise RuntimeError("R2 not configured")
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expiry,
    )


def list_prefix(prefix: str) -> list[str]:
    """Every stored key under a prefix. Returns R2 object keys when R2 is on,
    else local keys relative to the storage/ dir (same shape as an R2 key), so
    callers can treat both the same."""
    client = _get_client()
    if client:
        keys = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    base = os.path.join("storage", prefix)
    keys = []
    for root, _, files in os.walk(base):
        for name in files:
            keys.append(os.path.relpath(os.path.join(root, name), "storage"))
    return keys


def delete_prefix(prefix: str) -> None:
    client = _get_client()
    if not client:
        return
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=_bucket(), Key=obj["Key"])


def archive_prefix(src_prefix: str, dst_prefix: str) -> int:
    """Move every object under src_prefix to dst_prefix (server-side copy +
    delete). Returns the count moved; no-op (0) if R2 is off."""
    client = _get_client()
    if not client:
        return 0
    bucket = _bucket()
    moved = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=src_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            dst = dst_prefix + key[len(src_prefix):]
            client.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": key},
                Key=dst,
            )
            client.delete_object(Bucket=bucket, Key=key)
            moved += 1
    return moved
