"""FastAPI 앱 부트 테스트."""
from fastapi.testclient import TestClient

from server.app import create_app


def test_create_app_boots() -> None:
    """앱이 정상적으로 생성되고 응답을 반환한다."""
    client = TestClient(create_app())

    # 정적 자산 요청
    asset = client.get("/assets/missing.js")
    assert asset.status_code in (404, 405)

    # SPA 폴백 페이지 요청 (아직 static 미들웨어 구현 전)
    page = client.get("/jobs/abc")
    assert page.status_code in (404, 405)
