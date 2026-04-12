import httpx


class AgentProxy:
    def __init__(self, config):
        self.config = config
        self._client = httpx.AsyncClient(timeout=30.0, verify=False)

    async def forward_get(self, ip: str, port: int, path: str, params: dict | None = None) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.get(url, params=params)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_post(self, ip: str, port: int, path: str, body: dict | None = None) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.post(url, json=body)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_delete(self, ip: str, port: int, path: str) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.delete(url)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_put(self, ip: str, port: int, path: str, body: dict) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.put(url, json=body)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def check_health(self, ip: str, port: int) -> dict:
        try:
            result = await self.forward_get(ip, port, "/health")
            return result["body"]
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
