import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth.jwt import decode_token
from app.config.settings import Settings

PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        header = request.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token"})

        try:
            payload = decode_token(header.removeprefix("Bearer "), self.settings.auth)
            user_id = payload.get("sub")
            if not user_id:
                return JSONResponse(status_code=401, content={"detail": "Missing sub claim"})
            request.state.user_id = str(user_id)
        except jwt.PyJWTError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        return await call_next(request)
