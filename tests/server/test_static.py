"""FastAPI 앱 부트 및 정적 서빙 테스트."""
from fastapi.testclient import TestClient

from server.app import create_app


def test_create_app_boots() -> None:
    """앱이 정상적으로 생성된다."""
    app = create_app()
    assert app is not None
    assert app.state is not None


def test_missing_js_asset_is_404_not_index(tmp_path, monkeypatch) -> None:
    """확장자가 있는 자산이 없으면 404를 반환하고 index.html 폴백을 하지 않는다."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    monkeypatch.setattr("server.app.DIST_DIR", dist)
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    with TestClient(create_app()) as client:
        asset = client.get("/assets/missing.js")
        page = client.get("/jobs/abc")
    assert asset.status_code == 404
    assert page.status_code == 200
    assert "app" in page.text
