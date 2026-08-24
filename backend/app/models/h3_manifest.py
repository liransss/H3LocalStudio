from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class H3ModelFile:
    id: str
    filename: str
    model_dir: str
    size: int
    sha256: str
    repo: str
    revision: str
    required: bool = True
    compatible_families: tuple[str, ...] = ("fl2va", "ref2va")

    @property
    def role(self) -> str:
        if self.model_dir == "diffusion_models":
            return "diffusion_model"
        if self.model_dir == "text_encoders":
            return "text_encoder"
        if self.model_dir == "loras":
            return "turbo_lora"
        return "audio_vae" if "audio" in self.id else "video_vae"

    @property
    def url(self) -> str:
        # The official repository mirrors ComfyUI's model subdirectories.
        # Keeping that directory in the source path is significant: resolving
        # the filename at the repository root returns 404.
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.model_dir}/{self.filename}"

    def destination(self, comfyui_root: Path) -> Path:
        return comfyui_root / "models" / self.model_dir / self.filename


@dataclass(frozen=True)
class H3ModelManifest:
    version: str
    workflow_repo: str
    workflow_revision: str
    files: tuple[H3ModelFile, ...]
    families: dict[str, tuple[str, ...]]

    def validate(self) -> None:
        by_id = {item.id: item for item in self.files}
        if len(by_id) != len(self.files):
            raise ValueError("H3 manifest contains duplicate component IDs")
        for item in self.files:
            if item.model_dir not in {"diffusion_models", "text_encoders", "vae", "loras"}:
                raise ValueError(f"Unsupported ComfyUI model directory: {item.model_dir}")
            if item.size <= 0 or len(item.sha256) != 64:
                raise ValueError(f"Invalid metadata for {item.id}")
        for family, component_ids in self.families.items():
            unknown = set(component_ids).difference(by_id)
            if unknown:
                raise ValueError(f"{family} references unknown components: {sorted(unknown)}")
            incompatible = [component_id for component_id in component_ids if family not in by_id[component_id].compatible_families]
            if incompatible:
                raise ValueError(f"{family} contains incompatible components: {incompatible}")

    def component(self, component_id: str) -> H3ModelFile:
        return next(item for item in self.files if item.id == component_id)

    def family_files(self, family: str) -> tuple[H3ModelFile, ...]:
        try:
            return tuple(self.component(item) for item in self.families[family])
        except KeyError as error:
            raise ValueError(f"Unknown H3 model family: {family}") from error

    def family_size(self, family: str) -> int:
        return sum(item.size for item in self.family_files(family))


_BASE_REVISION = "3f57e8291d2ef846f9a074b1b76d2767db434abe"
_REPO = "Comfy-Org/MiniMax-H3"

H3_MANIFEST = H3ModelManifest(
    version="2026.08.24-ref2va.1",
    workflow_repo="Comfy-Org/workflow_templates",
    workflow_revision="0e0f4577453136eaa1c0e9d4b700e3e5ce5bb416",
    files=(
        H3ModelFile(
            "fl2va_diffusion",
            "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "diffusion_models",
            20_970_379_616,
            "e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a",
            _REPO,
            _BASE_REVISION,
            compatible_families=("fl2va",),
        ),
        H3ModelFile(
            "ref2va_diffusion",
            "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "diffusion_models",
            20_970_379_616,
            "9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779",
            _REPO,
            _BASE_REVISION,
            compatible_families=("ref2va",),
        ),
        H3ModelFile(
            "text_encoder",
            "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "text_encoders",
            15_687_142_551,
            "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
            _REPO,
            _BASE_REVISION,
        ),
        H3ModelFile(
            "video_vae",
            "minimax_h3_video_vae_fp16.safetensors",
            "vae",
            5_207_808_496,
            "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522",
            _REPO,
            _BASE_REVISION,
        ),
        H3ModelFile(
            "audio_vae",
            "minimax_h3_audio_vae_fp32.safetensors",
            "vae",
            605_254_808,
            "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48",
            _REPO,
            _BASE_REVISION,
        ),
        H3ModelFile(
            "fl2va_turbo_lora",
            "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
            "loras",
            1_956_193_000,
            "2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e",
            _REPO,
            "186455f4c2a878eb57d5c7916c5b0f71a77e8ceb",
            compatible_families=("fl2va",),
        ),
        H3ModelFile(
            "ref2va_turbo_lora",
            "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
            "loras",
            1_956_193_000,
            "5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c",
            _REPO,
            "edc77b088b1cb17f00cc1a57f68f263e82f9cc1d",
            compatible_families=("ref2va",),
        ),
    ),
    families={
        "fl2va": ("fl2va_diffusion", "text_encoder", "video_vae", "audio_vae", "fl2va_turbo_lora"),
        "ref2va": ("ref2va_diffusion", "text_encoder", "video_vae", "audio_vae", "ref2va_turbo_lora"),
    },
)

H3_MANIFEST.validate()
