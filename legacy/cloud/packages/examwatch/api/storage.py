"""Storage capabilities are issued only after room and parent checks."""
import hashlib
from pathlib import Path
import time
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from .security import capability


class Storage:
    bucket = "evidence"

    def __init__(self, config):
        self.config = config
        self.root = config.data_dir / "assets"
        if config.env != "production":
            self.root.mkdir(parents=True, exist_ok=True)

    def path(self, asset):
        # object_path is built by the server from validated UUIDs, never supplied by a client.
        path = (self.root / asset.object_path).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise HTTPException(400, "Invalid object path")
        return path

    def headers(self):
        return {"Authorization": f"Bearer {self.config.supabase_key}", "apikey": self.config.supabase_key}

    def request(self, method, path, **kwargs):
        try:
            response = httpx.request(method, f"{self.config.supabase_url}/storage/v1{path}", headers=self.headers(), timeout=60, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.RequestError, httpx.HTTPStatusError):
            raise HTTPException(502, "Không truy cập được kho bằng chứng") from None

    def url(self, asset, action, base_url):
        if self.config.env == "production":
            obj = quote(asset.object_path, safe="/")
            if action == "upload":
                response = self.request("POST", f"/object/upload/sign/{self.bucket}/{obj}", json={"upsert": False}).json()
                relative = response.get("url") or response.get("signedURL")
                method = "PUT"
            else:
                response = self.request("POST", f"/object/sign/{self.bucket}/{obj}", json={"expiresIn": 300}).json()
                relative = response.get("signedURL") or response.get("signedUrl")
                method = "GET"
            if not relative:
                raise HTTPException(502, "Kho bằng chứng không trả liên kết")
            url = relative if relative.startswith("https://") else f"{self.config.supabase_url}/storage/v1{relative}"
            return {"url": url, "method": method, "expires_in": 7200 if action == "upload" else 300}
        expires = int(time.time()) + 300
        signature = capability(self.config.signing_secret, asset.id, action, expires)
        return {"url": f"{base_url.rstrip('/')}/v1/assets/{asset.id}/content?action={action}&expires={expires}&signature={signature}", "method": "PUT" if action == "upload" else "GET", "expires_in": 300}

    def verify(self, asset):
        checksum = hashlib.sha256()
        size = 0
        if self.config.env == "production":
            try:
                with httpx.stream("GET", f"{self.config.supabase_url}/storage/v1/object/authenticated/{self.bucket}/{quote(asset.object_path, safe='/')}", headers=self.headers(), timeout=60) as response:
                    response.raise_for_status()
                    for block in response.iter_bytes(1024 * 1024):
                        size += len(block)
                        if size > asset.size_bytes:
                            break
                        checksum.update(block)
            except httpx.HTTPError:
                raise HTTPException(409, "Bằng chứng chưa tải xong") from None
        else:
            path = self.path(asset)
            if not path.exists():
                raise HTTPException(409, "Bằng chứng chưa tải xong")
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(block)
                    checksum.update(block)
        if size != asset.size_bytes or checksum.hexdigest() != asset.sha256:
            raise HTTPException(409, "Kích thước hoặc checksum không khớp")

    def delete(self, asset):
        if self.config.env == "production":
            self.request("DELETE", f"/object/{self.bucket}", json={"prefixes": [asset.object_path]})
        else:
            self.path(asset).unlink(missing_ok=True)
