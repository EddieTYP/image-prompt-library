from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.db import connect, init_db
from backend.main import create_app
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository


@pytest.mark.parametrize("count", [None, 3])
def test_creation_receipt_survives_response_loss_and_repository_restart(tmp_path, count):
    repo = GenerationJobRepository(tmp_path)
    payload = GenerationJobCreate(prompt_text="test", provider="openai_codex_oauth_native")
    request_id = str(uuid4())

    def submit(repository):
        return (repository.create_job(payload, request_id=request_id) if count is None
                else repository.create_job_set(payload, count, request_id=request_id))

    original = submit(repo)  # Commit succeeds but the caller loses the response.
    recovered = submit(GenerationJobRepository(tmp_path))
    assert recovered == original
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0] == (count or 1)
        assert conn.execute("SELECT COUNT(*) FROM generation_creation_requests").fetchone()[0] == 1
    with pytest.raises(GenerationJobConflict, match="different content"):
        repo.create_job(payload.model_copy(update={"prompt_text": "changed"}), request_id=request_id)
    # Reusing an ID for a different endpoint/count is also rejected.
    with pytest.raises(GenerationJobConflict, match="different content"):
        repo.create_job_set(payload, 5, request_id=request_id)


@pytest.mark.parametrize("count", [None, 3])
def test_concurrent_submissions_create_only_one_result(tmp_path, count):
    repositories = [GenerationJobRepository(tmp_path), GenerationJobRepository(tmp_path)]
    barrier = Barrier(2)
    payload = GenerationJobCreate(prompt_text="concurrent", provider="openai_codex_oauth_native")
    request_id = str(uuid4())

    def submit(repo):
        barrier.wait(timeout=5)
        return (repo.create_job(payload, request_id=request_id) if count is None
                else repo.create_job_set(payload, count, request_id=request_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(submit, repositories))
    assert first == second
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0] == (count or 1)


@pytest.mark.parametrize("count", [None, 3])
def test_job_and_receipt_are_atomic_on_failure(tmp_path, monkeypatch, count):
    repo = GenerationJobRepository(tmp_path)
    payload = GenerationJobCreate(prompt_text="rollback", provider="openai_codex_oauth_native")
    request_id = str(uuid4())
    method_name = "_create_job" if count is None else "_create_job_set"
    original = getattr(repo, method_name)

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("interrupted before receipt")

    with monkeypatch.context() as patch:
        patch.setattr(repo, method_name, fail_after_insert)
        with pytest.raises(RuntimeError, match="interrupted"):
            if count is None:
                repo.create_job(payload, request_id=request_id)
            else:
                repo.create_job_set(payload, count, request_id=request_id)
    with connect(tmp_path) as conn:
        for table in ("generation_jobs", "generation_sets", "generation_creation_requests"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    if count is None:
        repo.create_job(payload, request_id=request_id)
    else:
        repo.create_job_set(payload, count, request_id=request_id)
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0] == (count or 1)


@pytest.mark.parametrize("endpoint,count", [("", None), ("/sets", 3)])
def test_api_replays_original_job_and_validates_request_id(tmp_path, monkeypatch, endpoint, count):
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *a, **kw: None)
    monkeypatch.setattr("backend.routers.generation_jobs._continue_generation_queue", lambda *a, **kw: None)
    client = TestClient(create_app(library_path=tmp_path))
    job = {"prompt_text": "api replay", "provider": "openai_codex_oauth_native"}
    payload = job if count is None else {"job": job, "count": count}
    headers = {"Idempotency-Key": str(uuid4())}
    url = f"/api/generation-jobs{endpoint}"
    first = client.post(url, json=payload, headers=headers)
    assert first.status_code == 200
    second = client.post(url, json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert client.post(url, json=payload, headers={"Idempotency-Key": "invalid"}).status_code == 422
    job["prompt_text"] = "changed"
    assert client.post(url, json=payload, headers=headers).status_code == 409


def test_migration_is_repeatable_and_preserves_existing_jobs(tmp_path, monkeypatch):
    from backend import db
    with monkeypatch.context() as patch:
        patch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:-1])
        repo = GenerationJobRepository(tmp_path)
        original = repo.create_job(GenerationJobCreate(prompt_text="existing"))
    init_db(tmp_path)
    init_db(tmp_path)
    assert repo.get_job(original.id) == original


def test_missing_original_is_not_recreated(tmp_path):
    repo = GenerationJobRepository(tmp_path)
    payload = GenerationJobCreate(prompt_text="deleted original")
    request_id = str(uuid4())
    original = repo.create_job(payload, request_id=request_id)
    with connect(tmp_path) as conn:
        conn.execute("DELETE FROM generation_jobs WHERE id=?", (original.id,))
        conn.commit()
    with pytest.raises(GenerationJobConflict, match="will not be recreated"):
        repo.create_job(payload, request_id=request_id)


def test_backup_restore_preserves_creation_receipts(tmp_path):
    from backend.services.library_archives import backup_library, restore_library
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    payload = GenerationJobCreate(prompt_text="receipt backup")
    request_id = str(uuid4())
    original = repo.create_job(payload, request_id=request_id)
    archive = backup_library(library, tmp_path / "backup.tar.gz")
    target = tmp_path / "restored"
    restore_library(archive, target, confirm=True)
    assert GenerationJobRepository(target).create_job(payload, request_id=request_id).id == original.id


def test_backup_rejects_missing_creation_receipt_table(tmp_path):
    from backend.services.library_archives import LibraryArchiveError, backup_library
    GenerationJobRepository(tmp_path / "library")
    with connect(tmp_path / "library") as conn:
        conn.execute("DROP TABLE generation_creation_requests")
        conn.commit()
    with pytest.raises(LibraryArchiveError, match="missing required table"):
        backup_library(tmp_path / "library", tmp_path / "backup.tar.gz")


@pytest.mark.parametrize("count", [None, 3])
def test_receipt_failure_rolls_back_jobs_and_new_reference_clones(tmp_path, count):
    repo = GenerationJobRepository(tmp_path)
    source = tmp_path / "generation-results" / "gen_source" / "source.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "orange").save(source)
    payload = GenerationJobCreate(prompt_text="reference rollback", provider="openai_codex_oauth_native",
                                  parameters={"input_images": [{"result_path": "generation-results/gen_source/source.png"}]})
    with connect(tmp_path) as conn:
        conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON generation_creation_requests BEGIN SELECT RAISE(ABORT, 'receipt failure'); END")
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="receipt failure"):
        if count is None:
            repo.create_job(payload, request_id=str(uuid4()))
        else:
            repo.create_job_set(payload, count, request_id=str(uuid4()))
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0] == 0
    assert not list((tmp_path / "generation-references").glob("*/*"))
    assert source.is_file()
