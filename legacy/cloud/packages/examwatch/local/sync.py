import json
import httpx


class Sync:
    def __init__(self, store, base_url, token, client=None):
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=60)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.status = "Chưa đồng bộ"

    def send(self, method, path, payload=None):
        response = self.client.request(method, self.base_url + path, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def once(self):
        row = self.store.peek()
        if not row:
            return False
        payload = json.loads(row["payload"])
        try:
            kind = row["kind"]
            if kind == "session":
                self.send("POST", "/v1/sessions", payload)
            elif kind == "end":
                self.send("POST", f"/v1/sessions/{payload['id']}/end", {"ended_at": payload["ended_at"]})
            elif kind in ("event", "speech"):
                self.send("POST", "/v1/events:batch" if kind == "event" else "/v1/speech-segments:batch", {"items": [payload]})
            elif kind == "asset":
                local_path = payload.pop("local_path")
                info = self.send("POST", "/v1/assets/upload-url", payload)
                if info["status"] != "ready":
                    with open(local_path, "rb") as handle:
                        # Never forward the device bearer token to signed Storage URLs.
                        response = self.client.request(info["method"], info["url"], content=handle, headers={"Content-Type": payload["content_type"]})
                    # A previous upload may have completed before a process crash.
                    if response.status_code not in (200, 201, 204, 400, 409):
                        response.raise_for_status()
                    self.send("POST", f"/v1/assets/{payload['id']}/complete")
            else:
                raise ValueError("Unknown outbox type")
            self.store.ack(row["seq"])
            self.status = "Đã kết nối"
            return True
        except Exception as error:
            code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            self.status = f"Đồng bộ đang chờ ({code or type(error).__name__})"
            self.store.fail(row["seq"], self.status, permanent=code == 410)
            return False
