"""FastAPI 애플리케이션 팩토리."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

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
    return app


app = create_app()
