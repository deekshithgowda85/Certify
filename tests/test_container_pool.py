import threading
import time
from unittest.mock import MagicMock, patch


def make_mock_container(short_id="abc123"):
    c = MagicMock()
    c.short_id = short_id
    return c


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
