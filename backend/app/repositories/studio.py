from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.database import Database
from app.models.schemas import GenerationCreate, JobState, ProjectCreate, WorkflowCreate


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class StudioRepository:
    def __init__(self, database: Database):
        self.db = database

    def ensure_default_project(self) -> dict[str, Any]:
        row = self.db.fetchone("SELECT * FROM projects ORDER BY created_at LIMIT 1")
        if row:
            return dict(row)
        return self.create_project(ProjectCreate(name="My Creations", description="Default local project"))

    def create_project(self, request: ProjectCreate) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = utc_now()
        self.db.execute(
            "INSERT INTO projects(id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, request.name.strip(), request.description, now, now),
        )
        return dict(self.db.fetchone("SELECT * FROM projects WHERE id = ?", (project_id,)))

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.db.fetchall(
            """SELECT projects.*,
            (SELECT COUNT(*) FROM project_media_assets WHERE project_id = projects.id) AS reference_count
            FROM projects ORDER BY updated_at DESC"""
        )
        return [dict(row) for row in rows]

    def create_generation(
        self,
        request: GenerationCreate,
        seed: int,
        mode: str,
        is_mock: bool,
        resolved_references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        generation_id = str(uuid.uuid4())
        now = utc_now()
        parameters = request.model_dump(mode="json", exclude={"prompt", "project_id", "references", "seed", "mode"})
        references = resolved_references or [reference.model_dump(mode="json") for reference in request.references]
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO generations(
                    id, project_id, prompt, mode, seed, status, progress, stage,
                    parameters_json, references_json, is_mock, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 'Queued', ?, ?, ?, ?, ?)
                """,
                (
                    generation_id,
                    request.project_id,
                    request.prompt,
                    mode,
                    seed,
                    JobState.QUEUED,
                    json.dumps(parameters),
                    json.dumps(references),
                    int(is_mock),
                    now,
                    now,
                ),
            )
            for order, reference in enumerate(references):
                metadata = {
                    key: value
                    for key, value in reference.items()
                    if key not in {"asset_id", "id", "media_type", "role", "path", "notes", "order"}
                }
                connection.execute(
                    """INSERT INTO media_references(
                    id, generation_id, asset_id, media_type, role, path, sort_order, notes, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), generation_id, reference.get("asset_id") or reference.get("id"),
                        reference["media_type"], reference.get("role", "general"), reference.get("path", ""),
                        int(reference.get("order", order)), reference.get("notes", ""), json.dumps(metadata),
                    ),
                )
        return self.get_generation(generation_id)

    def find_media_asset_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM media_assets WHERE sha256 = ?", (sha256,))
        return self._decode_media_asset(row) if row else None

    def get_media_asset(self, asset_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM media_assets WHERE id = ?", (asset_id,))
        return self._decode_media_asset(row) if row else None

    def list_project_media_assets(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.db.fetchall(
            """SELECT media_assets.* FROM media_assets
            JOIN project_media_assets ON project_media_assets.asset_id = media_assets.id
            WHERE project_media_assets.project_id = ?
            ORDER BY project_media_assets.created_at DESC""",
            (project_id,),
        )
        return [self._decode_media_asset(row) for row in rows]

    def upsert_media_asset(self, asset: dict[str, Any], project_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO media_assets(
                id, sha256, filename, media_type, path, preview_path, size_bytes, duration,
                width, height, audio_present, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET updated_at = excluded.updated_at""",
                (
                    asset["id"], asset["sha256"], asset["filename"], asset["media_type"], asset["path"],
                    asset.get("preview_path"), int(asset["size_bytes"]), asset.get("duration"),
                    asset.get("width"), asset.get("height"), int(bool(asset.get("audio_present"))),
                    json.dumps(asset.get("metadata", {})), asset.get("created_at", now), now,
                ),
            )
            row = connection.execute("SELECT * FROM media_assets WHERE sha256 = ?", (asset["sha256"],)).fetchone()
            connection.execute(
                """INSERT INTO project_media_assets(project_id, asset_id, created_at)
                VALUES (?, ?, ?) ON CONFLICT(project_id, asset_id) DO NOTHING""",
                (project_id, row["id"], now),
            )
        return self.get_media_asset(row["id"])

    def update_generation(self, generation_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_generation(generation_id)
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self.db.execute(
            f"UPDATE generations SET {assignments} WHERE id = ?",  # noqa: S608 - keys are internal only
            (*fields.values(), generation_id),
        )
        return self.get_generation(generation_id)

    def get_generation(self, generation_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM generations WHERE id = ?", (generation_id,))
        return self._decode_generation(row) if row else None

    def list_generations(
        self, *, search: str | None = None, mode: str | None = None, project_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if search:
            clauses.append("prompt LIKE ?")
            values.append(f"%{search}%")
        if mode:
            clauses.append("mode = ?")
            values.append(mode)
        if project_id:
            clauses.append("project_id = ?")
            values.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(min(max(limit, 1), 500))
        rows = self.db.fetchall(
            f"SELECT * FROM generations {where} ORDER BY created_at DESC LIMIT ?",  # noqa: S608
            values,
        )
        return [self._decode_generation(row) for row in rows]

    def delete_generation(self, generation_id: str) -> dict[str, Any] | None:
        generation = self.get_generation(generation_id)
        if generation:
            self.db.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
        return generation

    def create_job(self, generation_id: str, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = utc_now()
        self.db.execute(
            """
            INSERT INTO jobs(id, generation_id, kind, status, progress, stage, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, 'Queued', ?, ?, ?)
            """,
            (job_id, generation_id, kind, JobState.QUEUED, json.dumps(payload or {}), now, now),
        )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["execution_metadata"] = json.loads(result.pop("execution_metadata_json", "{}"))
        return result

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_job(job_id)
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self.db.execute(
            f"UPDATE jobs SET {assignments} WHERE id = ?",  # noqa: S608 - keys are internal only
            (*fields.values(), job_id),
        )
        return self.get_job(job_id)

    def recover_interrupted_jobs(self) -> None:
        now = utc_now()
        message = "The application closed before this local job finished. Start it again from History."
        with self.db.connect() as connection:
            active = (JobState.QUEUED, JobState.PREPARING, JobState.RUNNING, JobState.UPSCALING, JobState.POST_PROCESSING)
            placeholders = ", ".join("?" for _ in active)
            connection.execute(
                f"""UPDATE jobs SET status = CASE WHEN kind = 'upscale' THEN ? ELSE ? END,
                stage = 'Interrupted', error_message = ?, completed_at = ?, updated_at = ?
                WHERE status IN ({placeholders})""",  # noqa: S608 - fixed placeholders only
                (JobState.UPSCALE_FAILED, JobState.FAILED, message, now, now, *active),
            )
            connection.execute(
                """UPDATE generations SET status = ?, stage = 'Interrupted', error_message = ?, completed_at = ?, updated_at = ?
                WHERE id IN (SELECT generation_id FROM jobs WHERE kind = 'generation' AND status = ? AND completed_at = ?)""",
                (JobState.FAILED, message, now, now, JobState.FAILED, now),
            )
            connection.execute(
                """UPDATE generations SET status = ?, stage = 'Upscale interrupted', error_message = ?, updated_at = ?
                WHERE id IN (SELECT generation_id FROM jobs WHERE kind = 'upscale' AND status = ? AND completed_at = ?)""",
                (JobState.UPSCALE_FAILED, message, now, JobState.UPSCALE_FAILED, now),
            )

    def add_generation_file(
        self, generation_id: str, kind: str, path: str, width: int | None = None, height: int | None = None
    ) -> None:
        self.db.execute(
            "INSERT INTO generation_files(id, generation_id, kind, path, width, height, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), generation_id, kind, path, width, height, utc_now()),
        )

    def upsert_generation_variant(
        self,
        generation_id: str,
        variant: str,
        provider_id: str,
        path: str,
        status: str,
        *,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
        duration: float | None = None,
        audio_present: bool = False,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        self.db.execute(
            """INSERT INTO generation_variants(
                id, generation_id, variant, provider_id, path, status, width, height, fps, duration,
                audio_present, error_message, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generation_id, variant) DO UPDATE SET
                provider_id = excluded.provider_id,
                path = excluded.path,
                status = excluded.status,
                width = excluded.width,
                height = excluded.height,
                fps = excluded.fps,
                duration = excluded.duration,
                audio_present = excluded.audio_present,
                error_message = excluded.error_message,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at""",
            (
                str(uuid.uuid4()), generation_id, variant, provider_id, path, status, width, height, fps, duration,
                int(audio_present), error_message, json.dumps(metadata or {}), now, now,
            ),
        )

    def get_generation_variant(self, generation_id: str, variant: str) -> dict[str, Any] | None:
        row = self.db.fetchone(
            "SELECT * FROM generation_variants WHERE generation_id = ? AND variant = ?",
            (generation_id, variant),
        )
        return self._decode_variant(row) if row else None

    def active_upscale_job(self, generation_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone(
            """SELECT id FROM jobs WHERE generation_id = ? AND kind = 'upscale'
            AND status IN (?, ?, ?, ?) ORDER BY created_at DESC LIMIT 1""",
            (generation_id, JobState.QUEUED, JobState.PREPARING, JobState.UPSCALING, JobState.POST_PROCESSING),
        )
        return self.get_job(row["id"]) if row else None

    def save_setting(self, key: str, value: Any) -> None:
        self.db.execute(
            """INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at""",
            (key, json.dumps(value), utc_now()),
        )

    def get_settings(self) -> dict[str, Any]:
        return {row["key"]: json.loads(row["value_json"]) for row in self.db.fetchall("SELECT * FROM settings")}

    def create_workflow(self, request: WorkflowCreate) -> dict[str, Any]:
        workflow_id = str(uuid.uuid4())
        now = utc_now()
        self.db.execute(
            "INSERT INTO workflows(id, project_id, name, graph_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (workflow_id, request.project_id, request.name, request.graph.model_dump_json(), now, now),
        )
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        if not row:
            return None
        result = dict(row)
        result["graph"] = json.loads(result.pop("graph_json"))
        return result

    def list_workflows(self) -> list[dict[str, Any]]:
        return [self.get_workflow(row["id"]) for row in self.db.fetchall("SELECT id FROM workflows ORDER BY updated_at DESC")]

    def _decode_generation(self, row: Any) -> dict[str, Any]:
        result = dict(row)
        result["parameters"] = json.loads(result.pop("parameters_json"))
        result["references"] = json.loads(result.pop("references_json"))
        result["output_metadata"] = json.loads(result.pop("output_metadata_json", "{}"))
        result["is_mock"] = bool(result["is_mock"])
        original_path = result["original_path"]
        result["original_url"] = f"/api/media/{result['id']}/original" if original_path else None
        result["output_url"] = f"/api/media/{result['id']}/output" if result["output_path"] else None
        result["thumbnail_url"] = f"/api/media/{result['id']}/thumbnail" if result["thumbnail_path"] else None
        rows = self.db.fetchall(
            "SELECT * FROM generation_variants WHERE generation_id = ? ORDER BY created_at",
            (result["id"],),
        )
        variants = [self._decode_variant(item) for item in rows]
        if original_path and not any(item["variant"] == "original" for item in variants):
            metadata = result["output_metadata"]
            variants.insert(
                0,
                {
                    "variant": "original",
                    "provider_id": metadata.get("workflow_family", "mock" if result["is_mock"] else "minimax_h3"),
                    "status": "completed",
                    "url": f"/api/media/{result['id']}/original",
                    "width": metadata.get("width"),
                    "height": metadata.get("height"),
                    "fps": metadata.get("fps"),
                    "duration": metadata.get("duration"),
                    "audio_present": bool(metadata.get("audio_present")),
                    "error_message": None,
                    "metadata": metadata,
                },
            )
        result["variants"] = variants
        result.pop("original_path", None)
        result.pop("output_path", None)
        result.pop("thumbnail_path", None)
        return result

    @staticmethod
    def _decode_media_asset(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["audio_present"] = bool(result["audio_present"])
        result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
        return result

    @staticmethod
    def _decode_variant(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["audio_present"] = bool(result["audio_present"])
        result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
        path = result.pop("path")
        result["url"] = (
            f"/api/media/{result['generation_id']}/{result['variant']}"
            if path and result["status"] == "completed"
            else None
        )
        result.pop("id", None)
        result.pop("created_at", None)
        result.pop("updated_at", None)
        return result
