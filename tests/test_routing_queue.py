from app.api.routers.jobs import compact_result_payload
from app.workers.tasks import process_command_job, process_test_job
from app.workers.worker_settings import WorkerSettings


def test_generic_worker_functions_are_registered_without_timeout_changes():
    assert WorkerSettings.functions == [process_test_job, process_command_job]
    assert WorkerSettings.max_jobs == 10
    assert WorkerSettings.job_timeout == 135.0
    assert WorkerSettings.keep_result == 3600


def test_default_job_response_hides_full_routes():
    compact = compact_result_payload(
        {
            "status": "ok",
            "routes": [{"geometry": "encoded-polyline"}],
            "warnings": [],
        }
    )

    assert compact is not None
    assert "routes" not in compact
    assert compact["routes_hidden"] is True
    assert compact["routes_count"] == 1
    assert compact["warnings"] == []
