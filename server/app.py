"""FastAPI 애플리케이션 팩토리."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from server.config import JOBS_ROOT, MAX_CONCURRENT_JOBS
from server.jobs import JobStore
from server.routes import router

logger = logging.getLogger(__name__)
DIST_DIR: Path = Path(__file__).resolve().parent.parent / "docs/prototype/img2txt-web/dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 JobStore를 관리한다."""
    app.state.job_store = JobStore(JOBS_ROOT, MAX_CONCURRENT_JOBS)
    if not DIST_DIR.exists():
        logger.warning(f"프런트 빌드 디렉토리가 없습니다: {DIST_DIR}")
    yield
    app.state.job_store.shutdown()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성하고 라우트를 등록한다."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(Exception)
    async def _on_error(request: Request, exc: Exception) -> JSONResponse:
        """미처리 예외를 500 오류로 반환한다(스택 및 내부 경로 노출 금지)."""
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """정적 자산 서빙과 SPA 폴백."""
        # /api/로 시작하면 404
        if full_path.startswith("api/"):
            return PlainTextResponse("not found", status_code=404)

        # DIST_DIR 내에서 해당 파일 존재 여부 확인 (경로 이탈 방지)
        candidate = (DIST_DIR / full_path).resolve()
        if candidate.is_file() and DIST_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)

        # 확장자가 있는 자산인데 없으면 404
        if Path(full_path).suffix:
            return PlainTextResponse("not found", status_code=404)

        # 확장자 없는 화면 경로면 index.html 폴백
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)

        # index.html도 없으면 200 안내 문구
        return PlainTextResponse(
            "프런트 빌드가 없습니다. `npm run build` 후 재시작하세요.", status_code=200
        )

    return app


app = create_app()
