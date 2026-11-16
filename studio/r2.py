"""Cloudflare R2 Object Storage integration for Clips X.

Zero-egress S3-compatible cloud storage for clips, videos, thumbnails, and audio.
Files can be served directly from Cloudflare's global edge network via public custom domain
or presigned URLs, eliminating bandwidth load on the local Clips X server.
"""
import datetime
import hashlib
import hmac
import mimetypes
import os
import threading
import urllib.parse
from pathlib import Path

import httpx

from . import config

_lock = threading.RLock()


def is_enabled() -> bool:
    """True if R2 storage is turned on and configured with credentials."""
    enabled = config.env("R2_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    if not enabled:
        return False
    return bool(account_id() and access_key() and secret_key() and bucket_name())


def account_id() -> str:
    return (config.env("R2_ACCOUNT_ID") or config.env("CLOUDFLARE_ACCOUNT_ID") or "").strip()


def access_key() -> str:
    return (config.env("R2_ACCESS_KEY_ID") or "").strip()


def secret_key() -> str:
    return (config.env("R2_SECRET_ACCESS_KEY") or "").strip()


def bucket_name() -> str:
    return (config.env("R2_BUCKET_NAME") or "clipsx-media").strip()


def public_url() -> str:
    """The public URL or custom domain for the R2 bucket (e.g. https://media.yourdomain.com)."""
    return (config.env("R2_PUBLIC_URL") or "").rstrip("/")


def region() -> str:
    return (config.env("R2_REGION") or "auto").strip()


def endpoint_url() -> str:
    """Cloudflare R2 S3 API endpoint."""
    acc = account_id()
    if not acc:
        return ""
    return f"https://{acc}.r2.cloudflarestorage.com"


# ------------------------------------------------------------------ AWS SigV4 Signer
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    return _sign(k_service, "aws4_request")


def _signed_request(method: str, path: str, query: dict = None, headers: dict = None, body: bytes = b"") -> httpx.Request:
    """Build a signed AWS SigV4 request for Cloudflare R2."""
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    host = f"{account_id()}.r2.cloudflarestorage.com"
    service = "s3"
    reg = region()

    # Clean path and query
    norm_path = "/" + path.lstrip("/")
    query_str = urllib.parse.urlencode(sorted((query or {}).items()))

    # Calculate payload hash
    payload_hash = hashlib.sha256(body).hexdigest()

    req_headers = {k.lower(): str(v).strip() for k, v in (headers or {}).items()}
    req_headers["host"] = host
    req_headers["x-amz-date"] = amz_date
    req_headers["x-amz-content-sha256"] = payload_hash

    # Canonical headers
    sorted_headers = sorted(req_headers.items())
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted_headers)
    signed_headers = ";".join(k for k, _ in sorted_headers)

    canonical_request = "\n".join([
        method.upper(),
        norm_path,
        query_str,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{reg}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _get_signature_key(secret_key(), date_stamp, reg, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key()}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    req_headers["authorization"] = auth_header

    full_url = f"https://{host}{norm_path}" + (f"?{query_str}" if query_str else "")
    return httpx.Request(method.upper(), full_url, headers=req_headers, content=body)


# ------------------------------------------------------------------ High-level Operations
def upload_file(local_path: Path, remote_key: str, content_type: str = None) -> dict:
    """Upload a local file to Cloudflare R2."""
    if not is_enabled():
        return {"ok": False, "error": "R2 is not enabled"}
    local_path = Path(local_path)
    if not local_path.is_file():
        return {"ok": False, "error": "Source file not found"}

    if not content_type:
        content_type, _ = mimetypes.guess_type(str(local_path))
        if not content_type:
            content_type = "video/mp4" if local_path.suffix == ".mp4" else "application/octet-stream"

    body = local_path.read_bytes()
    remote_key = remote_key.lstrip("/")
    path = f"{bucket_name()}/{remote_key}"

    headers = {
        "content-type": content_type,
        "content-length": str(len(body)),
    }

    req = _signed_request("PUT", path, headers=headers, body=body)
    with httpx.Client(timeout=120) as client:
        resp = client.send(req)
        if resp.status_code not in (200, 201):
            return {"ok": False, "error": f"R2 upload failed ({resp.status_code}): {resp.text[:200]}"}

    url = f"{public_url()}/{remote_key}" if public_url() else get_url(remote_key)
    return {"ok": True, "key": remote_key, "url": url, "size": len(body)}


def upload_bytes(data: bytes, remote_key: str, content_type: str = "application/octet-stream") -> dict:
    """Upload in-memory bytes to Cloudflare R2."""
    if not is_enabled():
        return {"ok": False, "error": "R2 is not enabled"}

    remote_key = remote_key.lstrip("/")
    path = f"{bucket_name()}/{remote_key}"

    headers = {
        "content-type": content_type,
        "content-length": str(len(data)),
    }

    req = _signed_request("PUT", path, headers=headers, body=data)
    with httpx.Client(timeout=120) as client:
        resp = client.send(req)
        if resp.status_code not in (200, 201):
            return {"ok": False, "error": f"R2 upload failed ({resp.status_code}): {resp.text[:200]}"}

    url = f"{public_url()}/{remote_key}" if public_url() else get_url(remote_key)
    return {"ok": True, "key": remote_key, "url": url, "size": len(data)}


def download_file(remote_key: str, dest_path: Path) -> bool:
    """Download a file from Cloudflare R2 to a local file."""
    if not is_enabled():
        return False
    remote_key = remote_key.lstrip("/")
    path = f"{bucket_name()}/{remote_key}"

    req = _signed_request("GET", path)
    with httpx.Client(timeout=120) as client:
        resp = client.send(req)
        if resp.status_code == 200:
            dest_path = Path(dest_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.content)
            return True
    return False


def delete_file(remote_key: str) -> bool:
    """Delete a single object from Cloudflare R2."""
    if not is_enabled():
        return False
    remote_key = remote_key.lstrip("/")
    path = f"{bucket_name()}/{remote_key}"

    req = _signed_request("DELETE", path)
    with httpx.Client(timeout=30) as client:
        resp = client.send(req)
        return resp.status_code in (200, 204)


def delete_prefix(prefix: str) -> int:
    """List and delete all objects starting with prefix (e.g. clips/job-id/)."""
    if not is_enabled():
        return 0
    prefix = prefix.lstrip("/")
    path = bucket_name()
    query = {"prefix": prefix, "max-keys": "100"}

    deleted = 0
    while True:
        req = _signed_request("GET", path, query=query)
        with httpx.Client(timeout=30) as client:
            resp = client.send(req)
            if resp.status_code != 200:
                break
            # Quick XML parse of Key elements
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(resp.content)
                ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
                keys = [elem.text for elem in root.findall(".//s3:Key", ns) or root.findall(".//Key")]
                if not keys:
                    break
                for k in keys:
                    if delete_file(k):
                        deleted += 1
                is_truncated = (root.findtext(".//s3:IsTruncated", namespaces=ns) or root.findtext(".//IsTruncated") or "").lower() == "true"
                if not is_truncated:
                    break
                next_marker = root.findtext(".//s3:NextContinuationToken", namespaces=ns) or root.findtext(".//NextMarker")
                if not next_marker:
                    break
                query["continuation-token"] = next_marker
            except Exception:
                break
    return deleted


def exists(remote_key: str) -> bool:
    """Check if an object exists in Cloudflare R2."""
    if not is_enabled():
        return False
    remote_key = remote_key.lstrip("/")
    path = f"{bucket_name()}/{remote_key}"
    req = _signed_request("HEAD", path)
    with httpx.Client(timeout=15) as client:
        resp = client.send(req)
        return resp.status_code == 200


def get_url(remote_key: str, expires_in: int = 86400) -> str:
    """Get a public URL or generate a signed Presigned URL for an R2 object."""
    remote_key = remote_key.lstrip("/")
    if public_url():
        return f"{public_url()}/{remote_key}"

    # Generate presigned SigV4 GET URL
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    host = f"{account_id()}.r2.cloudflarestorage.com"
    service = "s3"
    reg = region()
    credential_scope = f"{date_stamp}/{reg}/{service}/aws4_request"

    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key()}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in),
        "X-Amz-SignedHeaders": "host",
    }

    norm_path = f"/{bucket_name()}/{remote_key}"
    canonical_query = urllib.parse.urlencode(sorted(query_params.items()))
    canonical_headers = f"host:{host}\n"

    canonical_request = "\n".join([
        "GET",
        norm_path,
        canonical_query,
        canonical_headers,
        "host",
        "UNSIGNED-PAYLOAD",
    ])

    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _get_signature_key(secret_key(), date_stamp, reg, service)
    sig = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"https://{host}{norm_path}?{canonical_query}&X-Amz-Signature={sig}"


def test_connection() -> dict:
    """Test Cloudflare R2 connection by performing a head/list on the bucket."""
    if not is_enabled():
        return {"ok": False, "error": "R2 is not configured. Please check your .env settings."}

    path = bucket_name()
    req = _signed_request("GET", path, query={"max-keys": "1"})
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.send(req)
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "bucket": bucket_name(),
                    "account": account_id()[:6] + "…",
                    "public_url": public_url() or "Private (presigned URLs)",
                }
            return {
                "ok": False,
                "status": resp.status_code,
                "error": resp.text[:200] or f"HTTP {resp.status_code}",
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def status() -> dict:
    """Public summary for settings dashboard."""
    return {
        "enabled": is_enabled(),
        "bucket": bucket_name() if is_enabled() else "",
        "public_url": public_url() if is_enabled() else "",
    }
