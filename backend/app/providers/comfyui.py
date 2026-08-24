from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse

import httpx
import websockets

from app.models.h3_manifest import H3_MANIFEST
from app.providers.base import GenerationArtifact, ProgressCallback, VideoGenerationProvider
from app.services.model_store import H3ModelStore
from app.services.resource_monitor import ResourceTelemetry, generation_resource_guard
from app.workflows.h3_ref2va import H3Ref2VAWorkflowAdapter
from app.workflows.h3_t2v import H3Workflow, build_h3_t2v_workflow


logger = logging.getLogger(__name__)


class ComfyUIUnavailable(RuntimeError):
    pass


class ComfyUIIncompatible(RuntimeError):
    pass


class ComfyUIExecutionError(RuntimeError):
    pass


class RuntimeController(Protocol):
    async def ensure_running(self) -> dict[str, Any]: ...


def is_compatible_version(version: str | None, minimum: tuple[int, int, int] = (0, 30, 0)) -> bool | None:
    if not version:
        return None
    try:
        numeric = version.lstrip("v").split("+", 1)[0].split("-", 1)[0]
        parts = tuple(int(part) for part in numeric.split(".")[:3])
        padded = parts + (0,) * (3 - len(parts))
        return padded >= minimum
    except (ValueError, TypeError):
        return None


def parse_output_descriptor(
    history_payload: dict[str, Any], prompt_id: str, output_node_id: str | None = None
) -> dict[str, str]:
    entry = history_payload.get(prompt_id, history_payload)
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    preferred = [output_node_id] if output_node_id else []
    node_ids = preferred + [node_id for node_id in outputs if node_id not in preferred]
    for node_id in node_ids:
        node_output = outputs.get(node_id, {})
        for collection_name in ("images", "videos", "gifs"):
            for artifact in node_output.get(collection_name, []):
                filename = artifact.get("filename")
                if filename and Path(filename).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
                    return {
                        "filename": filename,
                        "subfolder": artifact.get("subfolder", ""),
                        "type": artifact.get("type", "output"),
                    }
    raise ComfyUIExecutionError("ComfyUI finished without reporting a generated video artifact")


class ComfyUIClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def _http(self, **kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, **kwargs)

    @property
    def websocket_url(self) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}/ws"

    async def health(self) -> dict[str, Any]:
        try:
            async with self._http(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                response.raise_for_status()
                payload = response.json()
            version = payload.get("system", {}).get("comfyui_version")
            return {
                "running": True,
                "version": version,
                "compatible": is_compatible_version(version),
                "url": self.base_url,
                "error": None,
            }
        except Exception as error:
            detail = str(error).strip() or type(error).__name__
            return {"running": False, "version": None, "compatible": None, "url": self.base_url, "error": detail}

    async def object_info(self) -> dict[str, Any]:
        async with self._http(timeout=20) as client:
            response = await client.get(f"{self.base_url}/object_info")
            response.raise_for_status()
            return response.json()

    async def validate_nodes(self, required: set[str] | frozenset[str]) -> None:
        available = await self.object_info()
        missing = sorted(set(required).difference(available))
        if missing:
            raise ComfyUIIncompatible(
                "Your ComfyUI version does not support the installed MiniMax H3 workflow. Missing nodes: "
                + ", ".join(missing)
            )

    async def execute(
        self,
        workflow: Any,
        progress: ProgressCallback,
        on_queued: Callable[[str], None] | None = None,
        on_node: Callable[[str], None] | None = None,
        node_stage: Callable[[str], str] | None = None,
        node_progress: Callable[[str], float] | None = None,
        progress_bounds: tuple[float, float] = (0.12, 0.85),
    ) -> tuple[str, dict[str, Any]]:
        client_id = str(uuid.uuid4())
        websocket_url = f"{self.websocket_url}?{urlencode({'clientId': client_id})}"
        try:
            async with websockets.connect(websocket_url, max_size=None, open_timeout=20) as socket:
                prompt_id = await self._queue_prompt(workflow.prompt, client_id)
                logger.info("ComfyUI queued prompt_id=%s client_id=%s", prompt_id, client_id)
                if on_queued:
                    on_queued(prompt_id)
                async with asyncio.timeout(6 * 60 * 60):
                    while True:
                        message = await socket.recv()
                        if not isinstance(message, str):
                            continue
                        event = json.loads(message)
                        data = event.get("data", {})
                        if data.get("prompt_id") not in {None, prompt_id}:
                            continue
                        event_type = event.get("type")
                        if event_type == "execution_error":
                            detail = data.get("exception_message") or data.get("exception_type") or "unknown ComfyUI error"
                            raise ComfyUIExecutionError(str(detail))
                        if event_type == "execution_interrupted":
                            raise asyncio.CancelledError
                        if event_type == "progress":
                            maximum = max(int(data.get("max", 1)), 1)
                            fraction = min(max(float(data.get("value", 0)) / maximum, 0), 1)
                            lower, upper = progress_bounds
                            await progress(lower + (upper - lower) * fraction, "Running local AI inference")
                        elif event_type == "executing":
                            node_id = data.get("node")
                            if node_id is None:
                                break
                            class_type = workflow.prompt.get(str(node_id), {}).get("class_type", "")
                            if on_node:
                                on_node(class_type)
                            await progress(
                                (node_progress or _node_progress)(class_type),
                                (node_stage or _node_stage)(class_type),
                            )
                        elif event_type == "execution_success":
                            break
                return prompt_id, await self.history(prompt_id)
        except (OSError, websockets.WebSocketException) as error:
            raise ComfyUIUnavailable(f"Local inference engine connection failed: {error}") from error

    async def _queue_prompt(self, prompt: dict[str, Any], client_id: str) -> str:
        async with self._http(timeout=30) as client:
            response = await client.post(f"{self.base_url}/prompt", json={"prompt": prompt, "client_id": client_id})
            if response.is_error:
                raise ComfyUIExecutionError(f"ComfyUI rejected the workflow: {response.text[:2000]}")
            payload = response.json()
        if payload.get("node_errors"):
            raise ComfyUIExecutionError(f"ComfyUI workflow validation failed: {json.dumps(payload['node_errors'])[:3000]}")
        prompt_id = payload.get("prompt_id")
        if not prompt_id:
            raise ComfyUIExecutionError("ComfyUI did not return a prompt ID")
        return str(prompt_id)

    async def history(self, prompt_id: str) -> dict[str, Any]:
        async with self._http(timeout=30) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            return response.json()

    async def download_output(self, descriptor: dict[str, str], destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        query = urlencode(descriptor)
        try:
            async with self._http(timeout=httpx.Timeout(60, read=600)) as client:
                async with client.stream("GET", f"{self.base_url}/view?{query}") as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        async for chunk in response.aiter_bytes(8 * 1024 * 1024):
                            output.write(chunk)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, destination)
        return destination

    async def interrupt(self) -> None:
        async with self._http(timeout=5) as client:
            response = await client.post(f"{self.base_url}/interrupt")
            response.raise_for_status()

    async def free_memory(self) -> None:
        async with self._http(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/free",
                json={"unload_models": True, "free_memory": True},
            )
            response.raise_for_status()

    async def cancel_prompt(self, prompt_id: str | None) -> None:
        async with self._http(timeout=5) as client:
            if prompt_id:
                await client.post(f"{self.base_url}/queue", json={"delete": [prompt_id]})
            response = await client.post(f"{self.base_url}/interrupt")
            response.raise_for_status()


class MiniMaxH3Provider(VideoGenerationProvider):
    def __init__(self, client: ComfyUIClient, models: H3ModelStore, runtime: RuntimeController):
        self.client = client
        self.models = models
        self.runtime = runtime
        self.active_prompt_id: str | None = None
        self.ref2va = H3Ref2VAWorkflowAdapter()

    async def generate(
        self, generation_id: str, parameters: dict[str, Any], output_dir: Path, progress: ProgressCallback
    ) -> GenerationArtifact:
        mode = str(parameters.get("mode", "t2v"))
        family = "ref2va" if mode == "r2v" else "fl2va"
        references = [dict(item) for item in parameters.get("references", [])]
        self.models.require_family(family)
        await progress(0.06, "Starting local inference engine")
        health = await self.runtime.ensure_running()
        if not health.get("running"):
            raise ComfyUIUnavailable("Local inference engine is not running")
        if health.get("compatible") is False:
            raise ComfyUIIncompatible("MiniMax H3 requires ComfyUI 0.30.0 or newer.")
        await progress(0.07, "Unloading previous models")
        try:
            await self.client.free_memory()
        except Exception as error:
            logger.warning("ComfyUI preflight memory cleanup failed: %s", error)
        preflight = generation_resource_guard(ref2va=family == "ref2va", reference_count=len(references))
        if preflight["warnings"]:
            await progress(0.075, preflight["warnings"][0])

        staged_dir: Path | None = None
        telemetry = ResourceTelemetry()
        telemetry.start()
        prompt_id: str | None = None
        workflow: H3Workflow | None = None
        destination: Path | None = None
        logger.info(
            "H3 generation job=%s family=%s parameters=%s ComfyUI=%s preflight=%s",
            generation_id,
            family,
            {key: value for key, value in parameters.items() if key not in {"prompt", "references"}},
            health.get("version"),
            preflight,
        )
        try:
            if references:
                staged_dir, references = await asyncio.to_thread(self._stage_references, generation_id, references)
            workflow_parameters = {
                **parameters,
                "references": references,
                "generation_id": generation_id,
            }
            workflow = (
                self.ref2va.build(workflow_parameters)
                if family == "ref2va"
                else build_h3_t2v_workflow(workflow_parameters)
            )
            await self.client.validate_nodes(workflow.required_node_classes)
            logger.info("H3 workflow job=%s models=%s metadata=%s", generation_id, workflow.model_files, workflow.metadata)
            await progress(0.1, "Submitting native H3 Ref2VA workflow" if family == "ref2va" else "Submitting native H3 workflow")
            prompt_id, history = await self.client.execute(
                workflow, progress, lambda queued_id: setattr(self, "active_prompt_id", queued_id)
            )
            logger.info("H3 generation job=%s prompt_id=%s", generation_id, prompt_id)
            descriptor = parse_output_descriptor(history, prompt_id, workflow.output_node_id)
            await progress(0.88, "Importing ComfyUI output")
            destination = output_dir / f"{generation_id}_original.mp4"
            await self.client.download_output(descriptor, destination)
            logger.info("H3 output job=%s path=%s", generation_id, destination)
        finally:
            self.active_prompt_id = None
            await telemetry.stop()
            if staged_dir:
                await asyncio.to_thread(self._clean_staged_references, staged_dir)
            try:
                await self.client.free_memory()
            except Exception as error:
                logger.warning("ComfyUI post-generation memory cleanup failed: %s", error)
        if not destination or not workflow:
            raise ComfyUIExecutionError("ComfyUI did not produce a local H3 output")
        return GenerationArtifact(
            path=destination,
            provider_job_id=prompt_id,
            workflow_family=family,
            model_files=workflow.model_files,
            manifest_version=H3_MANIFEST.version,
            metadata={
                **(workflow.metadata or {}),
                "resource_preflight": preflight,
                "resource_telemetry": telemetry.summary(),
            },
        )

    async def cancel(self) -> None:
        try:
            await self.client.cancel_prompt(self.active_prompt_id)
        finally:
            self.active_prompt_id = None

    def _stage_references(
        self, generation_id: str, references: list[dict[str, Any]]
    ) -> tuple[Path, list[dict[str, Any]]]:
        input_root = self.models.comfyui_root / "input"
        stage_dir = input_root / "H3LocalStudio" / "ref2va" / generation_id
        stage_dir.mkdir(parents=True, exist_ok=False)
        staged: list[dict[str, Any]] = []
        try:
            for index, reference in enumerate(references):
                source = Path(reference["path"])
                if not source.is_file():
                    raise ValueError(f"Reference file is missing: {reference.get('filename', source.name)}")
                filename = f"{index:02d}_{uuid.uuid4().hex}{source.suffix.lower()}"
                destination = stage_dir / filename
                shutil.copy2(source, destination)
                staged.append(
                    {
                        **reference,
                        "comfyui_path": destination.relative_to(input_root).as_posix(),
                    }
                )
            return stage_dir, staged
        except BaseException:
            self._clean_staged_references(stage_dir)
            raise

    def _clean_staged_references(self, stage_dir: Path) -> None:
        expected_parent = (self.models.comfyui_root / "input" / "H3LocalStudio" / "ref2va").resolve()
        resolved = stage_dir.resolve()
        if resolved.parent != expected_parent:
            raise RuntimeError("Refusing to clean a reference staging path outside the managed input directory")
        shutil.rmtree(resolved, ignore_errors=True)


def _node_stage(class_type: str) -> str:
    return {
        "UNETLoader": "Loading H3 diffusion model",
        "CLIPLoader": "Loading H3 text encoder",
        "VAELoader": "Loading H3 VAE",
        "MiniMaxH3ImageToVideo": "Encoding prompt",
        "MiniMaxH3ReferenceToVideo": "Encoding references and prompt",
        "LoadImage": "Loading image references",
        "LoadVideo": "Loading video references",
        "LoadAudio": "Loading audio references",
        "GetVideoComponents": "Reading reference video and soundtrack",
        "SamplerCustomAdvanced": "Generating video",
        "VAEDecode": "Decoding video",
        "VAEDecodeAudio": "Decoding native audio",
        "CreateVideo": "Muxing video and audio",
        "SaveVideo": "Saving ComfyUI output",
    }.get(class_type, "Running H3 workflow")


def _node_progress(class_type: str) -> float:
    return {
        "UNETLoader": 0.13,
        "CLIPLoader": 0.14,
        "VAELoader": 0.15,
        "MiniMaxH3ImageToVideo": 0.18,
        "MiniMaxH3ReferenceToVideo": 0.18,
        "LoadImage": 0.11,
        "LoadVideo": 0.11,
        "LoadAudio": 0.11,
        "GetVideoComponents": 0.12,
        "SamplerCustomAdvanced": 0.2,
        "VAEDecode": 0.84,
        "VAEDecodeAudio": 0.85,
        "CreateVideo": 0.86,
        "SaveVideo": 0.87,
    }.get(class_type, 0.16)
