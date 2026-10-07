import logging
import os
import threading
import time

import docker

from app.config import settings

logger = logging.getLogger(__name__)
MAX_POOL_CONTAINERS = 5


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

    MIN_IDLE = 2  -> always keep 2 warm and ready
    MAX_TOTAL = 5 -> hard ceiling, never exceed

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

    def __init__(self, min_idle: int = 2, max_total: int = MAX_POOL_CONTAINERS):
        self.MAX_TOTAL = min(max(1, max_total), MAX_POOL_CONTAINERS)
        self.MIN_IDLE = min(max(0, min_idle), self.MAX_TOTAL)

        self.idle: list = []        # warm containers, ready
        self.busy: dict = {}        # job_id -> container
        self._next_container_number = 1

        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        self._boot()

    def _boot(self):
        """Start MIN_IDLE containers on pool creation."""
        logger.info(f"ContainerPool booting {self.MIN_IDLE} idle containers...")
        for _ in range(self.MIN_IDLE):
            try:
                c = self._start_container()
                self.idle.append(c)
                logger.info(f"Idle container started: {c.short_id}")
            except Exception as e:
                logger.error(f"Failed to boot idle container: {e}")

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
                except Exception:
                    pass
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
                except Exception as e:
                    logger.warning(f"Error removing container: {e}")

            # Notify any tasks waiting in acquire()
            self._condition.notify_all()

    def status(self) -> dict:
        """Return current pool state - used by the pool status endpoint."""
        with self._lock:
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
            }

    def shutdown(self):
        """Stop all containers cleanly. Call on worker shutdown."""
        with self._lock:
            all_containers = list(self.idle) + list(self.busy.values())
            for c in all_containers:
                try:
                    c.stop(timeout=5)
                    c.remove(force=True)
                except Exception:
                    pass
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
                    min_idle=2,
                    max_total=MAX_POOL_CONTAINERS,
                )
            return self._pool

    def acquire(self, job_id: str, timeout: float | None = None):
        return self._get().acquire(job_id, timeout=timeout)

    def release(self, job_id: str):
        if self._pool is not None:
            self._pool.release(job_id)

    def status(self) -> dict:
        if self._pool is None:
            return {
                "idle": 0, "busy": 0, "idle_container_ids": [], "busy_jobs": {},
                "min_idle": 2,
                "max_total": MAX_POOL_CONTAINERS,
            }
        return self._pool.status()

    def shutdown(self):
        if self._pool is not None:
            self._pool.shutdown()


# Global singleton - one pool per dispatcher process
pool = _LazyPool()
