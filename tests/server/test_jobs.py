"""잡 저장소와 안전 재시도 핵심 테스트."""
from pathlib import Path
from unittest.mock import MagicMock

from img2txt.scanner import collect_images
from server.jobs import JobStore
from server.models import JobOptions


def test_create_job_naturally_sorts_files_and_uses_internal_names(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()  # type: ignore[method-assign]

    job_id = store.create_job(
        [("page-10.jpg", b"10"), ("page-2.jpg", b"2")],
        JobOptions(correct=False),
    )

    job = store.get_job(job_id)
    assert job is not None
    assert [file.filename for file in job.files] == ["page-2.jpg", "page-10.jpg"]
    assert [file.pageNumber for file in job.files] == [1, 2]
    saved = collect_images(tmp_path / job_id / "uploads")
    assert len(saved) == 2
    assert saved[0].name.endswith("page-0001.jpg")
    store.shutdown()
