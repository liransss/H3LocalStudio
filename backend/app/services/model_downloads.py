from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.models.h3_manifest import H3ModelFile


class DownloadCancelled(RuntimeError):
    pass


@dataclass
class ModelOperation:
    id: str
    kind: str
    family: str
    status: str = "queued"
    bytes_done: int = 0
    total_bytes: int = 0
    current_file: str | None = None
    message: str = "Queued"
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "family": self.family,
            "status": self.status,
            "bytes_done": self.bytes_done,
            "total_bytes": self.total_bytes,
            "current_file": self.current_file,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
        }


class ModelDownloadManager:
    def __init__(
        self,
        store: Any,
        transport: httpx.AsyncBaseTransport | None = None,
        prepare_install: Callable[[str, bool], Awaitable[None]] | None = None,
    ):
        self.store = store
        self.transport = transport
        self.prepare_install = prepare_install
        self.operations: dict[str, ModelOperation] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def start_install(self, family: str, *, repair: bool = False) -> dict[str, Any]:
        self._assert_no_active(family)
        operation = ModelOperation(
            id=str(uuid.uuid4()),
            kind="repair" if repair else "install",
            family=family,
            total_bytes=self.store.manifest.family_size(family),
        )
        self.operations[operation.id] = operation
        self.tasks[operation.id] = asyncio.create_task(self._install(operation, repair), name=f"model-{operation.id}")
        return operation.public()

    def start_verify(self, family: str) -> dict[str, Any]:
        self._assert_no_active(family)
        operation = ModelOperation(
            id=str(uuid.uuid4()),
            kind="verify",
            family=family,
            total_bytes=self.store.manifest.family_size(family),
        )
        self.operations[operation.id] = operation
        self.tasks[operation.id] = asyncio.create_task(self._verify(operation), name=f"model-{operation.id}")
        return operation.public()

    def get(self, operation_id: str) -> dict[str, Any] | None:
        operation = self.operations.get(operation_id)
        return operation.public() if operation else None

    def active_for(self, family: str) -> dict[str, Any] | None:
        for operation in self.operations.values():
            if operation.family == family and operation.status in {"queued", "running", "cancelling"}:
                return operation.public()
        return None

    def cancel(self, operation_id: str) -> dict[str, Any] | None:
        operation = self.operations.get(operation_id)
        if not operation:
            return None
        if operation.status in {"queued", "running"}:
            operation.status = "cancelling"
            operation.message = "Cancelling after the current disk write"
            operation.cancel_event.set()
        return operation.public()

    async def stop(self) -> None:
        for operation in self.operations.values():
            if operation.status in {"queued", "running", "cancelling"}:
                operation.cancel_event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    def _assert_no_active(self, family: str) -> None:
        if any(operation.status in {"queued", "running", "cancelling"} for operation in self.operations.values()):
            raise RuntimeError("Another model operation is already running; shared H3 components will not be downloaded twice")

    async def _install(self, operation: ModelOperation, repair: bool) -> None:
        try:
            operation.status = "running"
            if self.prepare_install:
                operation.message = "Preparing the pinned provider runtime"
                await self.prepare_install(operation.family, repair)
            files = self.store.manifest.family_files(operation.family)
            required = sum(self._remaining_bytes(item, repair) for item in files)
            self._check_disk_space(required)
            completed = operation.total_bytes - sum(item.size for item in files)
            for component in files:
                self._check_cancelled(operation)
                operation.current_file = component.filename
                status = self.store.component_status(component)["status"]
                if status in {"installed", "verified"}:
                    operation.message = f"Verifying {component.filename}"
                    if await self.store.verify_component(component):
                        completed += component.size
                        operation.bytes_done = completed
                        continue
                    status = "invalid"
                if status == "invalid" and not repair:
                    raise RuntimeError(f"{component.filename} failed validation. Choose Repair to replace it.")
                if status == "invalid":
                    self._preserve_invalid(self.store.path_for(component))
                downloaded = await self._download(component, operation, completed)
                completed += downloaded
                operation.bytes_done = completed
            operation.status = "completed"
            operation.current_file = None
            operation.message = "Models installed and SHA-256 verified"
        except DownloadCancelled:
            operation.status = "cancelled"
            operation.message = "Cancelled; partial downloads were kept for resume"
        except Exception as error:
            operation.status = "failed"
            operation.error = str(error)
            operation.message = "Model operation failed"

    async def _verify(self, operation: ModelOperation) -> None:
        try:
            operation.status = "running"
            completed = 0
            for component in self.store.manifest.family_files(operation.family):
                self._check_cancelled(operation)
                operation.current_file = component.filename
                operation.message = f"Verifying {component.filename}"
                if not await self.store.verify_component(component):
                    raise RuntimeError(f"{component.filename} is missing, the wrong size, or failed SHA-256 validation")
                completed += component.size
                operation.bytes_done = completed
            operation.status = "completed"
            operation.current_file = None
            operation.message = "All model checksums match the pinned manifest"
        except DownloadCancelled:
            operation.status = "cancelled"
            operation.message = "Verification cancelled"
        except Exception as error:
            operation.status = "failed"
            operation.error = str(error)
            operation.message = "Model verification failed"

    def _remaining_bytes(self, component: H3ModelFile, repair: bool) -> int:
        status = self.store.component_status(component)
        if status["status"] in {"installed", "verified"}:
            return 0
        if status["status"] == "partial" and not repair:
            return max(0, component.size - int(status["bytes_present"]))
        return component.size

    def _check_disk_space(self, required: int) -> None:
        root = self.store.comfyui_root
        root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(root).free
        reserve = 2 * 1024**3
        if free < required + reserve:
            raise RuntimeError(
                f"Not enough free disk space. Need {required + reserve:,} bytes including a 2 GiB safety reserve; "
                f"only {free:,} bytes are available."
            )

    async def _download(self, component: H3ModelFile, operation: ModelOperation, completed: int) -> int:
        destination = self.store.path_for(component)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f"{destination.name}.part")
        offset = partial.stat().st_size if partial.is_file() else 0
        if offset > component.size:
            self._preserve_invalid(partial)
            offset = 0
        digest = hashlib.sha256()
        if offset:
            operation.message = f"Checking partial file before resuming {component.filename}"
            await asyncio.to_thread(_update_digest, digest, partial)
            if offset == component.size:
                if digest.hexdigest() == component.sha256:
                    os.replace(partial, destination)
                    if await self.store.verify_component(component):
                        return component.size
                self._preserve_invalid(partial)
                offset = 0
                digest = hashlib.sha256()
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        timeout = httpx.Timeout(connect=30, read=60, write=60, pool=30)
        operation.message = f"Downloading {component.filename}"
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout, headers=headers, transport=self.transport
        ) as client:
            async with client.stream("GET", component.url) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    offset = 0
                    digest = hashlib.sha256()
                mode = "ab" if offset else "wb"
                with partial.open(mode) as target:
                    async for chunk in response.aiter_bytes(8 * 1024 * 1024):
                        self._check_cancelled(operation)
                        target.write(chunk)
                        digest.update(chunk)
                        offset += len(chunk)
                        operation.bytes_done = completed + offset
        if offset != component.size:
            raise RuntimeError(f"Downloaded size mismatch for {component.filename}: expected {component.size}, got {offset}")
        if digest.hexdigest() != component.sha256:
            self._preserve_invalid(partial)
            raise RuntimeError(f"SHA-256 mismatch for {component.filename}; the invalid download was preserved for diagnosis")
        os.replace(partial, destination)
        if not await self.store.verify_component(component):
            raise RuntimeError(f"Post-install verification failed for {component.filename}")
        return component.size

    @staticmethod
    def _check_cancelled(operation: ModelOperation) -> None:
        if operation.cancel_event.is_set():
            raise DownloadCancelled

    @staticmethod
    def _preserve_invalid(path: Path) -> None:
        if path.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            path.replace(path.with_name(f"{path.name}.invalid-{timestamp}"))


def _update_digest(digest: Any, path: Path) -> None:
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
