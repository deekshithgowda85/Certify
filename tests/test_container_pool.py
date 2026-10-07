import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def make_mock_container(short_id="abc123"):
    c = MagicMock()
    c.short_id = short_id
    c.name = f"sandbox-{short_id[-1]}"
    c.attrs = {"State": {"Status": "running", "Health": {"Status": "healthy"}}}
    c.stats.return_value = {}
    return c


def test_container_status_includes_runtime_metrics():
    from app.pool.container_pool import ContainerPool

    container = MagicMock()
    container.short_id = "abc123"
    container.name = "sandbox-1"
    container.attrs = {
        "Name": "/sandbox-1",
        "State": {
            "Status": "running",
            "StartedAt": datetime.now(timezone.utc).isoformat(),
            "Health": {"Status": "healthy"},
        },
    }
    container.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 250, "percpu_usage": [1, 2]},
            "system_cpu_usage": 2000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 150},
            "system_cpu_usage": 1000,
        },
        "memory_stats": {"usage": 104 * 1024 * 1024, "limit": 256 * 1024 * 1024},
    }

    result = ContainerPool._container_status(container, "busy")

    assert result["health"] == "healthy"
    assert result["role"] == "busy"
    assert result["cpu_percent"] == 20
    assert result["mem_used_mb"] == 104
    assert result["mem_limit_mb"] == 256
    assert result["uptime_seconds"] >= 0


@patch("app.pool.container_pool.client")
def test_boots_min_idle_on_start(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=5)
    assert len(pool.idle) == 2
    assert mock_docker.containers.run.call_count == 2
    names = [call.kwargs["name"] for call in mock_docker.containers.run.call_args_list]
    assert names == ["sandbox-1", "sandbox-2"]


@patch("app.pool.container_pool.client")
def test_acquire_uses_idle_first(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=5)
    initial_call_count = mock_docker.containers.run.call_count

    pool.acquire("job-1")

    # No new container started - used idle one
    assert mock_docker.containers.run.call_count == initial_call_count
    assert len(pool.idle) == 1
    assert len(pool.busy) == 1


@patch("app.pool.container_pool.client")
def test_acquire_starts_new_when_idle_empty(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=5)

    pool.acquire("job-1")   # uses idle[0]
    pool.acquire("job-2")   # uses idle[1]
    pool.acquire("job-3")   # idle empty -> starts new container

    assert len(pool.busy) == 3


@patch("app.pool.container_pool.client")
def test_release_returns_to_idle_when_below_min(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=5)

    pool.acquire("job-1")
    pool.acquire("job-2")
    # idle is now empty (0 < MIN_IDLE=2)

    pool.release("job-1")
    # should go back to idle not stopped
    assert len(pool.idle) == 1


@patch("app.pool.container_pool.client")
def test_release_stops_container_when_idle_full(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=5)

    pool.acquire("job-1")  # takes idle[0]
    pool.release("job-1")  # idle back to 2 = MIN_IDLE

    pool.acquire("job-2")  # takes idle[0] again
    pool.acquire("job-3")  # takes idle[1] - now idle empty

    pool.acquire("job-4")  # starts new container
    pool.release("job-2")  # idle goes to 1, keep warm
    pool.release("job-3")  # idle goes to 2 = MIN_IDLE
    pool.release("job-4")  # idle already at MIN_IDLE -> stop container

    assert mock_docker.containers.run.return_value.stop.called


@patch("app.pool.container_pool.client")
def test_blocks_when_at_max_total(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool
    pool = ContainerPool(min_idle=2, max_total=3)

    pool.acquire("job-1")
    pool.acquire("job-2")
    pool.acquire("job-3")
    # pool is now at MAX_TOTAL = 3

    acquired = []

    def try_acquire():
        c = pool.acquire("job-4")  # should block then get one
        acquired.append(c)

    t = threading.Thread(target=try_acquire, daemon=True)
    t.start()

    time.sleep(0.2)
    assert len(acquired) == 0  # still blocked

    pool.release("job-1")      # release one -> job-4 unblocks
    t.join(timeout=3)

    assert len(acquired) == 1  # job-4 got a container


@patch("app.pool.container_pool.client")
def test_pool_supports_configured_capacity_above_default(mock_docker):
    mock_docker.containers.run.return_value = make_mock_container()
    from app.pool.container_pool import ContainerPool

    pool = ContainerPool(min_idle=0, max_total=8)
    for index in range(8):
        pool.acquire(f"job-{index}")

    assert pool.MAX_TOTAL == 8
    assert len(pool.busy) == 8
    assert mock_docker.containers.run.call_count == 8


@patch("app.pool.container_pool.client")
def test_lazy_pool_start_boots_configured_warm_containers(mock_docker):
    mock_docker.containers.run.side_effect = [
        make_mock_container("warm001"),
        make_mock_container("warm002"),
    ]
    from app.pool.container_pool import pool

    pool.start()
    result = pool.status()

    assert result["idle"] == 2
    assert result["status"] == "healthy"
    assert [container["id"] for container in result["containers"]] == ["warm001", "warm002"]
