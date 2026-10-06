from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse


class CanonicalWebMiddleware(BaseHTTPMiddleware):
    """Redirect HTML page navigation without redirecting application traffic."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if (
            request.url.hostname == "personal.kvarteret.no"
            and request.method == "GET"
            and "text/html" in request.headers.get("accept", "").lower()
            and request.headers.get("sec-fetch-dest", "document") == "document"
            and not request.headers.get("hx-request")
            and not request.headers.get("authorization")
            and not request.url.path.startswith(("/api/", "/media/", "/images/", "/static/", "/internal/"))
            and request.url.path not in {"/docs", "/redoc", "/openapi.json"}
            and "text/html" in response.headers.get("content-type", "").lower()
        ):
            target = request.url.replace(scheme="https", netloc="personal.samfunnetibergen.no")
            return RedirectResponse(str(target), status_code=307, headers={"Cache-Control": "no-store", "Vary": "Accept, Sec-Fetch-Dest, HX-Request, Authorization"})
        return response
