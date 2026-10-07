import logging
import threading
import time
from datetime import datetime, timezone

import docker

from app.config import settings

logger = logging.getLogger(__name__)
SANDBOX_LABEL = "com.bulk-certificate-generator.sandbox"


class _LazyDockerClient:
    """`client` stays a module-level name, but the Docker connection is only opened on first use
    (docker.from_env() raises at import time when no daemon is reachable, e.g. in tests/CI)."""

    def __init__(self):
        self._client = None
        self._lock = threading.Lock()

    def __getattr__(self, item):
        if item.startswith("_"):  # keep introspection (mock.patch, copy, pickle) from opening a connection
            raise AttributeError(item)
        with self._lock:
            if self._client is None:
                self._client = docker.from_env()
        return getattr(self._client, item)


client = _LazyDockerClient()


class ContainerPool:
    """
    Manages a pool of pdf-generator Docker containers.

    MIN_IDLE -> configured number of warm containers
    MAX_TOTAL -> configured hard ceiling, never exceed

    States a container can be in:
      idle  -> running, no job assigned, ready immediately
      busy  -> running, assigned to a job
      (stopped containers are not tracked - they dont exist)

    On startup     -> boot MIN_IDLE idle containers
    Job arrives    -> pop from idle (instant, no cold start)
    Idle empty     -> start new container if busy < MAX_TOTAL
    At MAX_TOTAL   -> caller waits until one is released or times out
    Job done       -> if idle < MIN_IDLE: push back to idle
                      else: stop + remove container
    """

    def __init__(
        self,
        min_idle: int | None = None,
        max_total: int | None = None,
    ):
        configured_max = settings.SANDBOX_MAX_CONTAINERS if max_total is None else max_total
        configured_min = settings.SANDBOX_MIN_IDLE if min_idle is None else min_idle
        self.MAX_TOTAL = max(1, configured_max)
        self.MIN_IDLE = min(max(0, configured_min), self.MAX_TOTAL)

        self.idle: list = []        # warm containers, ready
        self.busy: dict = {}        # job_id -> container
        self._next_container_number = 1
        self.boot_errors = 0

        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        self._boot()

    def _boot(self):
        """Start MIN_IDLE containers on pool creation."""
        logger.info(f"ContainerPool booting {self.MIN_IDLE} idle containers...")
        try:
            running = client.containers.list(
                filters={"label": f"{SANDBOX_LABEL}=true"}
            )
            self._next_container_number = max(
                (
                    int(container.name.rsplit("-", 1)[1])
                    for container in running
                    if container.name.rsplit("-", 1)[-1].isdigit()
                ),
                default=0,
            ) + 1
            for container in running[:self.MIN_IDLE]:
                self.idle.append(container)
                logger.info("Reusing warm sandbox container: %s", container.name)
        except docker.errors.DockerException as exc:
            self.boot_errors += 1
            logger.error("Could not inspect existing sandbox containers: %s", exc)

        for _ in range(self.MIN_IDLE):
            if len(self.idle) >= self.MIN_IDLE:
                break
            try:
                c = self._start_container()
                self.idle.append(c)
                logger.info(f"Idle container started: {c.short_id}")
            except docker.errors.DockerException as e:
                self.boot_errors += 1
                logger.exception("Failed to boot idle sandbox container: %s", e)

    def _start_container(self):
        """
        Start a fresh pdf-generator container.
        Container runs a sleep loop waiting for work.
        It stays alive until pool explicitly stops it.
        """
        container_name = f"{settings.SANDBOX_CONTAINER_PREFIX}-{self._next_container_number}"
        container = client.containers.run(
            image=settings.SANDBOX_IMAGE,
            name=container_name,
            command="sleep infinity",   # keep alive, pool controls lifecycle
            detach=True,
            remove=False,
            network=settings.SANDBOX_NETWORK,
            volumes={
                settings.SANDBOX_VOLUME: {
                    "bind": "/output",
                    "mode": "rw"
                }
            },
            mem_limit=settings.SANDBOX_MEM_LIMIT,
            cpu_period=settings.SANDBOX_CPU_PERIOD,
            cpu_quota=settings.SANDBOX_CPU_QUOTA,
            labels={SANDBOX_LABEL: "true"},
        )
        self._next_container_number += 1
        return container

    def acquire(self, job_id: str, timeout: float | None = None):
        """
        Get a container for job_id.
        Waits for a container until timeout, then raises TimeoutError.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while True:
                # Case 1: idle container available - use it instantly
                if self.idle:
                    container = self.idle.pop(0)
                    self.busy[job_id] = container
                    logger.info(
                        f"Job {job_id} -> assigned idle container "
                        f"{container.short_id} | "
                        f"idle={len(self.idle)} busy={len(self.busy)}"
                    )
                    return container

                # Case 2: no idle but can start new one
                elif len(self.busy) < self.MAX_TOTAL:
                    container = self._start_container()
                    self.busy[job_id] = container
                    logger.info(
                        f"Job {job_id} -> started new container "
                        f"{container.short_id} | "
                        f"idle={len(self.idle)} busy={len(self.busy)}"
                    )
                    return container

                # Case 3: at MAX_TOTAL - wait for a release
                else:
                    logger.info(
                        f"Job {job_id} waiting - pool at max "
                        f"({self.MAX_TOTAL}). "
                        f"idle={len(self.idle)} busy={len(self.busy)}"
                    )
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"no container available for job {job_id} "
                                f"within {timeout} seconds"
                            )
                        wait_seconds = min(10, remaining)
                    else:
                        wait_seconds = 10
                    self._condition.wait(timeout=wait_seconds)
                    # Loop again after wait - check conditions

    def release(self, job_id: str):
        """
        Return container to pool after job finishes.
        Keep warm if idle < MIN_IDLE, else stop and remove.
        """
        with self._condition:
            container = self.busy.pop(job_id, None)
            if container is None:
                return

            if len(self.idle) < self.MIN_IDLE:
                # Reset container - kill any running process
                try:
                    container.exec_run("pkill -f generate.py",
                                       detach=True)
                except docker.errors.DockerException:
                    logger.debug("Could not reset sandbox container", exc_info=True)
                self.idle.append(container)
                logger.info(
                    f"Container {container.short_id} returned to idle | "
                    f"idle={len(self.idle)} busy={len(self.busy)}"
                )
            else:
                # Have enough idle - stop this container
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                    logger.info(
                        f"Container {container.short_id} stopped + removed | "
                        f"idle={len(self.idle)} busy={len(self.busy)}"
                    )
                except docker.errors.DockerException as e:
                    logger.warning(f"Error removing container: {e}")

            # Notify any tasks waiting in acquire()
            self._condition.notify_all()

    def status(self) -> dict:
        """Return current pool state - used by the pool status endpoint."""
        with self._lock:
            containers = [
                self._container_status(container, "busy" if container in self.busy.values() else "idle")
                for container in [*self.idle, *self.busy.values()]
            ]
            return {
                "idle": len(self.idle),
                "busy": len(self.busy),
                "idle_container_ids": [c.short_id for c in self.idle],
                "busy_jobs": {
                    job_id: c.short_id
                    for job_id, c in self.busy.items()
                },
                "min_idle": self.MIN_IDLE,
                "max_total": self.MAX_TOTAL,
                "status": (
                    "healthy"
                    if len(self.idle) + len(self.busy) >= self.MIN_IDLE
                    else "degraded"
                ),
                "boot_errors": self.boot_errors,
                "containers": containers,
            }

    @staticmethod
    def _container_status(container, role: str) -> dict:
        try:
            container.reload()
            attrs = container.attrs or {}
            state = attrs.get("State", {})
            container_state = state.get("Status", "unknown")
            health = state.get("Health", {}).get("Status")
            if health is None and container_state == "running":
                health = "healthy"
            health = health or "unknown"
            started_at = state.get("StartedAt")
            uptime_seconds = None
            if started_at and not started_at.startswith("0001-"):
                started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                uptime_seconds = max(0, time.time() - started.timestamp())

            cpu_percent = None
            mem_used_mb = None
            mem_limit_mb = None
            stats = container.stats(stream=False)
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            cpu_delta = (
                cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            )
            system_delta = (
                cpu_stats.get("system_cpu_usage", 0)
                - precpu_stats.get("system_cpu_usage", 0)
            )
            online_cpus = cpu_stats.get("online_cpus") or len(
                cpu_stats.get("cpu_usage", {}).get("percpu_usage", [])
            )
            if cpu_delta >= 0 and system_delta > 0 and online_cpus:
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100

            memory_stats = stats.get("memory_stats", {})
            memory_usage = memory_stats.get("usage")
            memory_limit = memory_stats.get("limit")
            if memory_usage is not None:
                mem_used_mb = memory_usage / (1024 * 1024)
            if memory_limit is not None:
                mem_limit_mb = memory_limit / (1024 * 1024)

            return {
                "id": container.short_id,
                "name": attrs.get("Name", container.name),
                "role": role,
                "status": container_state,
                "health": health,
                "cpu_percent": cpu_percent,
                "mem_used_mb": mem_used_mb,
                "mem_limit_mb": mem_limit_mb,
                "uptime_seconds": uptime_seconds,
            }
        except (AttributeError, docker.errors.DockerException) as exc:
            logger.warning("Could not inspect sandbox container: %s", exc)
            return {
                "id": getattr(container, "short_id", "unknown"),
                "name": getattr(container, "name", "unknown"),
                "role": role,
                "status": "unknown",
                "health": "unknown",
                "cpu_percent": None,
                "mem_used_mb": None,
                "mem_limit_mb": None,
                "uptime_seconds": None,
            }

    def shutdown(self):
        """Stop all containers cleanly. Call on worker shutdown."""
        with self._lock:
            all_containers = list(self.idle) + list(self.busy.values())
            known_ids = {getattr(container, "id", None) for container in all_containers}
            stale_containers = client.containers.list(
                all=True,
                filters={"name": f"{settings.SANDBOX_CONTAINER_PREFIX}-"},
            )
            for container in all_containers + [
                candidate for candidate in stale_containers
                if getattr(candidate, "id", None) not in known_ids
            ]:
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    logger.warning("Could not remove sandbox container during shutdown", exc_info=True)
            self.idle.clear()
            self.busy.clear()
            logger.info("ContainerPool shutdown complete.")


class _LazyPool:
    """Global singleton, created on first use instead of at import time, so importing the module
    never starts containers (and the worker shutdown hook never boots a pool just to stop it)."""

    def __init__(self):
        self._pool = None
        self._lock = threading.Lock()

    def _get(self) -> ContainerPool:
        with self._lock:
            if self._pool is None:
                self._pool = ContainerPool(
                    min_idle=settings.SANDBOX_MIN_IDLE,
                    max_total=settings.SANDBOX_MAX_CONTAINERS,
                )
            return self._pool

    def start(self) -> None:
        """Initialize the pool during worker startup so warm containers are always visible."""
        self._get()

    def acquire(self, job_id: str, timeout: float | None = None):
        return self._get().acquire(job_id, timeout=timeout)

    def release(self, job_id: str):
        if self._pool is not None:
            self._pool.release(job_id)

    def status(self) -> dict:
        if self._pool is None:
            return {
                "idle": 0, "busy": 0, "idle_container_ids": [], "busy_jobs": {},
                "min_idle": min(settings.SANDBOX_MIN_IDLE, settings.SANDBOX_MAX_CONTAINERS),
                "max_total": settings.SANDBOX_MAX_CONTAINERS,
                "status": "starting",
                "boot_errors": 0,
                "containers": [],
            }
        return self._pool.status()

    def shutdown(self):
        if self._pool is not None:
            self._pool.shutdown()


# Global singleton - one pool per dispatcher process
pool = _LazyPool()
