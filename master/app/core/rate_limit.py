import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_rpm: int = 120, login_rpm: int = 5, login_lockout_seconds: int = 900):
        super().__init__(app)
        self.default_rpm = default_rpm
        self.login_rpm = login_rpm
        self.login_lockout_seconds = login_lockout_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._login_failures: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, entries: list[float], window: float) -> list[float]:
        now = time.time()
        return [t for t in entries if now - t < window]

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        now = time.time()
        path = request.url.path

        # Login-specific rate limiting (brute force protection)
        if path == "/auth/login" and request.method == "POST":
            self._login_failures[client_ip] = self._cleanup(
                self._login_failures[client_ip], self.login_lockout_seconds
            )
            if len(self._login_failures[client_ip]) >= self.login_rpm:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many login attempts. Try again in {self.login_lockout_seconds // 60} minutes.",
                )

        # General rate limiting
        key = f"{client_ip}:{path}"
        self._requests[key] = self._cleanup(self._requests[key], 60)
        if len(self._requests[key]) >= self.default_rpm:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        self._requests[key].append(now)

        response = await call_next(request)

        # Track failed login attempts
        if path == "/auth/login" and request.method == "POST" and response.status_code == 401:
            self._login_failures[client_ip].append(now)

        return response
