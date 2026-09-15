import httpx

from core.plugin import BasePlugin, PluginContext, logger, register


class BearerAuth(httpx.Auth):
    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class MyPlugin(BasePlugin):
    def __init__(self, ctx: PluginContext, cfg: dict):
        super().__init__(ctx, cfg)

    async def initialize(self):
        self.server_url = self.plugin_cfg.get("server_url").rstrip("/")
        self.username = self.plugin_cfg.get("username")
        self.password = self.plugin_cfg.get("password")
        self._token = None
        self._client = httpx.AsyncClient(base_url=self.server_url)
        if any(not v for v in [self.server_url, self.username, self.password]):
            logger.error("[todo-api] Missing required configuration parameters: server_url, username, password")
            return
        await self._login()

    async def _login(self):
        try:
            resp = await self._client.post(
                "/api/v1/auth/login",
                json={"user_id": self.username, "password": self.password},
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            logger.info("[todo-api] Login OK")
        except Exception as e:
            logger.error(f"[todo-api] Login failed: {e}")

    async def terminate(self):
        await self._client.aclose()

    @register.tool(
        name="get_openapi_spec",
        description="Retrieve the OpenAPI specification for the TODO API",
        params={"type": "object", "properties": {}},
    )
    async def get_openapi_spec(self, *args, **kwargs):
        resp = await self._client.get("/openapi.json")
        return {"status": "success", "spec": resp.json()}

    @register.tool(
        name="todo_api_request",
        description="Make a request to the TODO API",
        params={
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "The HTTP method to use"},
                "endpoint": {"type": "string", "description": "The API endpoint to call"},
                "data": {"type": "object", "description": "The data to send with the request"},
            },
            "required": ["method", "endpoint"],
        },
    )
    async def todo_api_request(self, *_, method: str, endpoint: str, data: dict = None):
        auth = BearerAuth(self._token) if self._token else None
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        m = method.upper()
        if m == "GET":
            resp = await self._client.get(path, auth=auth)
        elif m == "POST":
            resp = await self._client.post(path, json=data, auth=auth)
        elif m == "PUT":
            resp = await self._client.put(path, json=data, auth=auth)
        elif m == "DELETE":
            resp = await self._client.delete(path, auth=auth)
        elif m == "PATCH":
            resp = await self._client.patch(path, json=data, auth=auth)
        else:
            return {"status": "error", "message": f"Unsupported HTTP method: {method}"}
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"status": "success", "status_code": resp.status_code, "data": body}
