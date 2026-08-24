from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class UpscalerModelFile:
    id: str
    filename: str
    model_dir: str
    source_path: str
    size: int
    sha256: str
    repo: str
    revision: str
    role: str
    compatible_families: tuple[str, ...]
    required: bool = True

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.source_path}"

    def destination(self, comfyui_root: Path) -> Path:
        return comfyui_root / "models" / Path(self.model_dir) / self.filename


@dataclass(frozen=True)
class UpscalerModelManifest:
    version: str
    files: tuple[UpscalerModelFile, ...]
    families: dict[str, tuple[str, ...]]
    family_names: dict[str, str]

    def validate(self) -> None:
        by_id = {item.id: item for item in self.files}
        if len(by_id) != len(self.files):
            raise ValueError("Upscaler manifest contains duplicate component IDs")
        for item in self.files:
            destination = PurePosixPath(item.model_dir.replace("\\", "/"))
            source = PurePosixPath(item.source_path)
            if destination.is_absolute() or ".." in destination.parts:
                raise ValueError(f"Unsafe model directory for {item.id}")
            if source.is_absolute() or ".." in source.parts:
                raise ValueError(f"Unsafe model source path for {item.id}")
            if item.size <= 0 or len(item.sha256) != 64:
                raise ValueError(f"Invalid metadata for {item.id}")
        for family, component_ids in self.families.items():
            unknown = set(component_ids).difference(by_id)
            if unknown:
                raise ValueError(f"{family} references unknown components: {sorted(unknown)}")
            incompatible = [component_id for component_id in component_ids if family not in by_id[component_id].compatible_families]
            if incompatible:
                raise ValueError(f"{family} contains incompatible components: {incompatible}")

    def component(self, component_id: str) -> UpscalerModelFile:
        return next(item for item in self.files if item.id == component_id)

    def family_files(self, family: str) -> tuple[UpscalerModelFile, ...]:
        try:
            return tuple(self.component(component_id) for component_id in self.families[family])
        except KeyError as error:
            raise ValueError(f"Unknown upscaler model family: {family}") from error

    def family_size(self, family: str) -> int:
        return sum(item.size for item in self.family_files(family))


_FLASH_REPO = "JunhaoZhuang/FlashVSR-v1.1"
_FLASH_REVISION = "27561b186ded3402d7c975f4fd722e2885b6135f"
_SEED_REPO = "Comfy-Org/SeedVR2"
_SEED_REVISION = "673340c8a66db62b84e4099def7d01d337ae12dc"

UPSCALER_MANIFEST = UpscalerModelManifest(
    version="2026.08.24-upscalers.1",
    files=(
        UpscalerModelFile(
            "flash_lq_projection", "LQ_proj_in.ckpt", "FlashVSR-v1.1", "LQ_proj_in.ckpt",
            575_694_948, "d6d011cdaaba6a52645086caa08fa04124e746f6ca568140a24007591142bfd2",
            _FLASH_REPO, _FLASH_REVISION, "conditioning_projection", ("flashvsr",),
        ),
        UpscalerModelFile(
            "flash_tiny_decoder", "TCDecoder.ckpt", "FlashVSR-v1.1", "TCDecoder.ckpt",
            189_018_333, "e224bdcf2f52745cbf4d393ff5374c2ba09e90285d5d19062d2bf63b915b6161",
            _FLASH_REPO, _FLASH_REVISION, "tiny_decoder", ("flashvsr",),
        ),
        UpscalerModelFile(
            "flash_vae", "Wan2.1_VAE.pth", "FlashVSR-v1.1", "Wan2.1_VAE.pth",
            507_609_880, "38071ab59bd94681c686fa51d75a1968f64e470262043be31f7a094e442fd981",
            _FLASH_REPO, _FLASH_REVISION, "video_vae", ("flashvsr",),
        ),
        UpscalerModelFile(
            "flash_diffusion", "diffusion_pytorch_model_streaming_dmd.safetensors", "FlashVSR-v1.1",
            "diffusion_pytorch_model_streaming_dmd.safetensors", 5_676_070_392,
            "bd28180edcf3446c028e32fc6b731a80bf7e4da2ab4caac3186b9499964d37be",
            _FLASH_REPO, _FLASH_REVISION, "diffusion_model", ("flashvsr",),
        ),
        UpscalerModelFile(
            "seedvr2_diffusion", "seedvr2_3b_int8_convrot.safetensors", "diffusion_models",
            "diffusion_models/seedvr2_3b_int8_convrot.safetensors", 3_458_259_704,
            "c3dec8bcc5916843a8a858572970597462e1f2dc598d6dfd818f6cd40f53a157",
            _SEED_REPO, _SEED_REVISION, "diffusion_model", ("seedvr2",),
        ),
        UpscalerModelFile(
            "seedvr2_vae", "seedvr2_ema_vae_fp16.safetensors", "vae",
            "vae/seedvr2_ema_vae_fp16.safetensors", 501_324_814,
            "20678548f420d98d26f11442d3528f8b8c94e57ee046ef93dbb7633da8612ca1",
            _SEED_REPO, _SEED_REVISION, "video_vae", ("seedvr2",),
        ),
    ),
    families={
        "flashvsr": ("flash_lq_projection", "flash_tiny_decoder", "flash_vae", "flash_diffusion"),
        "seedvr2": ("seedvr2_diffusion", "seedvr2_vae"),
    },
    family_names={"flashvsr": "FlashVSR v1.1 · Fast 1080p", "seedvr2": "SeedVR2 3B INT8 · Best Quality 1080p"},
)

UPSCALER_MANIFEST.validate()
