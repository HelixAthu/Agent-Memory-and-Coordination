"""Per-tenant FalkorDB connection layer with pooled async client and bounded concurrency."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from falkordb import FalkorDB

try:
    from falkordb.asyncio import FalkorDB as AsyncFalkorDB
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False

from memory_core.config import settings
from memory_core.errors import DatabaseError
from memory_core.tenancy import graph_name, validate_tenant_id

logger: logging.Logger = logging.getLogger("memory_core.db")


class TenantDB:
    """Manages asynchronous database interactions for a single tenant graph."""

    def __init__(self, tenant_id: str, max_inflight: int | None = None) -> None:
        self.tenant_id: str = validate_tenant_id(tenant_id)
        self.graph_name: str = graph_name(self.tenant_id)
        self.max_inflight: int = max_inflight or settings.max_inflight
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._async_client: AsyncFalkorDB | None = None
        self._async_graph: Any = None
        self._sync_client: FalkorDB = FalkorDB(host=settings.falkordb_host, port=settings.falkordb_port)

    def _ensure_async_client(self) -> tuple[asyncio.Semaphore, Any]:
        """Ensure semaphore and async graph connection belong to the current running event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._loop is None or self._loop != current_loop or self._loop.is_closed():
            self._loop = current_loop
            self._semaphore = asyncio.Semaphore(self.max_inflight)
            if HAS_ASYNC:
                self._async_client = AsyncFalkorDB(
                    host=settings.falkordb_host,
                    port=settings.falkordb_port,
                )
                self._async_graph = self._async_client.select_graph(self.graph_name)
            else:
                self._async_client = None
                self._async_graph = None

        sem = self._semaphore or asyncio.Semaphore(self.max_inflight)
        return sem, self._async_graph

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Retrieve the loop-bound semaphore for in-flight concurrency control."""
        sem, _ = self._ensure_async_client()
        return sem

    async def run_ro(self, cypher: str, params: dict[str, Any] | None = None) -> list[Any]:
        """Execute a read-only query using ro_query with semaphore and timing."""
        sem, async_g = self._ensure_async_client()
        async with sem:
            t0 = time.perf_counter()
            try:
                if async_g is not None:
                    res = await async_g.ro_query(cypher, params or {})
                    result_set = res.result_set
                else:
                    g = self._sync_client.select_graph(self.graph_name)
                    res = await asyncio.to_thread(g.ro_query, cypher, params or {})
                    result_set = res.result_set
                dur_ms = (time.perf_counter() - t0) * 1000
                logger.debug("[%s RO] in %.2fms: %s", self.graph_name, dur_ms, cypher[:60])
                return result_set
            except Exception as e:
                logger.exception("RO query error on %s: %s", self.graph_name, e)
                raise DatabaseError(f"RO query failed on {self.graph_name}: {e}") from e

    async def run_rw(self, cypher: str, params: dict[str, Any] | None = None) -> list[Any]:
        """Execute a read-write mutation query using query with semaphore and timing."""
        sem, async_g = self._ensure_async_client()
        async with sem:
            t0 = time.perf_counter()
            try:
                if async_g is not None:
                    res = await async_g.query(cypher, params or {})
                    result_set = res.result_set
                else:
                    g = self._sync_client.select_graph(self.graph_name)
                    res = await asyncio.to_thread(g.query, cypher, params or {})
                    result_set = res.result_set
                dur_ms = (time.perf_counter() - t0) * 1000
                logger.debug("[%s RW] in %.2fms: %s", self.graph_name, dur_ms, cypher[:60])
                return result_set
            except Exception as e:
                logger.exception("RW query error on %s: %s", self.graph_name, e)
                raise DatabaseError(f"RW query failed on {self.graph_name}: {e}") from e

    async def delete_graph(self) -> None:
        """Delete the tenant's FalkorDB graph."""
        _, async_g = self._ensure_async_client()
        try:
            if async_g is not None:
                await async_g.delete()
            else:
                await asyncio.to_thread(self._sync_client.select_graph(self.graph_name).delete)
        except Exception as e:
            # Graph might not exist yet, ignore
            logger.debug("Graph %s delete exception: %s", self.graph_name, e)


class TenantDBRegistry:
    """Registry maintaining a single TenantDB instance per tenant."""

    def __init__(self) -> None:
        self._instances: dict[str, TenantDB] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get(self, tenant_id: str) -> TenantDB:
        """Retrieve or create the TenantDB instance for the given tenant."""
        valid_id = validate_tenant_id(tenant_id)
        if valid_id in self._instances:
            return self._instances[valid_id]
        async with self._lock:
            if valid_id not in self._instances:
                self._instances[valid_id] = TenantDB(valid_id)
            return self._instances[valid_id]


registry: TenantDBRegistry = TenantDBRegistry()


async def get_tenant_db(tenant_id: str) -> TenantDB:
    """Convenience helper to retrieve the tenant's database manager."""
    return await registry.get(tenant_id)
