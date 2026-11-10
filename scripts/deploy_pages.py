"""Deploy web/ to Cloudflare Pages by direct upload.

    CLOUDFLARE_API_TOKEN=... uv run --with blake3 python scripts/deploy_pages.py

The demo page is static, so there is nothing to build: every file under web/
is uploaded as is. This follows the steps wrangler takes for `pages deploy`,
over the REST API, so no Node toolchain is needed:

  1. an upload token for the project
  2. a hash per file — BLAKE3 of the base64 contents plus the extension
  3. upload only the files Cloudflare does not already have
  4. a deployment whose manifest maps each path to its hash

The project uses direct upload rather than the GitHub integration, so a push
does not redeploy; run this again instead.
"""

import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
import urllib.request
import uuid

from blake3 import blake3

API = "https://api.cloudflare.com/client/v4"
PROJECT = os.environ.get("PAGES_PROJECT", "strawberry-harvest-bench")
WEB = Path(__file__).resolve().parents[1] / "web"
BATCH_BYTES = 40 * 1024 * 1024  # stay well under the API's request size limit


def call(method: str, url: str, token: str, body=None, headers=None) -> dict:
    data = None
    hdrs = {"Authorization": f"Bearer {token}", **(headers or {})}
    if body is not None and not isinstance(body, bytes):
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    elif isinstance(body, bytes):
        data = body
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req) as res:
            out = json.loads(res.read())
    except urllib.error.HTTPError as err:
        out = json.loads(err.read() or b"{}")
    if not out.get("success", False):
        raise SystemExit(f"{method} {url.split('/client/v4')[-1]} failed: {out.get('errors')}")
    return out.get("result")


def files() -> dict[str, Path]:
    return {"/" + p.relative_to(WEB).as_posix(): p
            for p in sorted(WEB.rglob("*")) if p.is_file() and not p.name.startswith(".")}


def file_hash(path: Path) -> str:
    contents = base64.b64encode(path.read_bytes()).decode()
    return blake3((contents + path.suffix.lstrip(".")).encode()).hexdigest()[:32]


def main() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise SystemExit("set CLOUDFLARE_API_TOKEN")
    account = call("GET", f"{API}/accounts", token)[0]["id"]
    jwt = call("GET", f"{API}/accounts/{account}/pages/projects/{PROJECT}/upload-token", token)["jwt"]

    manifest = {route: file_hash(p) for route, p in files().items()}
    paths = {h: files()[r] for r, h in manifest.items()}
    missing = call("POST", f"{API}/pages/assets/check-missing", jwt,
                   {"hashes": sorted(set(manifest.values()))})
    print(f"{len(manifest)} files, {len(missing)} to upload")

    batch, size = [], 0
    def flush():
        nonlocal batch, size
        if batch:
            call("POST", f"{API}/pages/assets/upload", jwt, batch)
            batch, size = [], 0
    for h in missing:
        p = paths[h]
        value = base64.b64encode(p.read_bytes()).decode()
        if size + len(value) > BATCH_BYTES:
            flush()
        batch.append({"key": h, "value": value, "base64": True,
                      "metadata": {"contentType": mimetypes.guess_type(p.name)[0]
                                   or "application/octet-stream"}})
        size += len(value)
    flush()
    call("POST", f"{API}/pages/assets/upsert-hashes", jwt, {"hashes": sorted(set(manifest.values()))})

    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("manifest", json.dumps(manifest)), ("branch", "main")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n')
    body = ("".join(parts) + f"--{boundary}--\r\n").encode()
    dep = call("POST", f"{API}/accounts/{account}/pages/projects/{PROJECT}/deployments", token,
               body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    print(f"deployed: {dep['url']}")
    print(f"project:  https://{PROJECT}.pages.dev")


if __name__ == "__main__":
    sys.exit(main())
