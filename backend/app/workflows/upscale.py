from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.upscaler_manifest import UPSCALER_MANIFEST


@dataclass(frozen=True)
class UpscaleWorkflow:
    prompt: dict[str, dict[str, Any]]
    output_node_id: str
    model_files: tuple[str, ...]
    required_node_classes: frozenset[str]
    provider_id: str


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def build_flashvsr_workflow(input_file: str, filename_prefix: str, seed: int) -> UpscaleWorkflow:
    graph = {
        "1": _node("LoadVideo", file=input_file),
        "2": _node("GetVideoComponents", video=["1", 0]),
        "3": _node(
            "FlashVSRInitPipe",
            model="FlashVSR-v1.1",
            mode="tiny",
            vae_model="Wan2.1",
            force_offload=True,
            precision="auto",
            device="cuda:0",
            attention_mode="sdpa",
        ),
        "4": _node(
            "FlashVSRNodeAdv",
            pipe=["3", 0],
            frames=["2", 0],
            scale=2,
            color_fix=True,
            tiled_vae=True,
            tiled_dit=True,
            tile_size=384,
            tile_overlap=32,
            unload_dit=True,
            sparse_ratio=2.0,
            kv_ratio=3.0,
            local_range=11,
            seed=seed,
            frame_chunk_size=21,
            enable_debug=True,
            keep_models_on_cpu=True,
            resize_factor=0.75,
        ),
        "5": _node("CreateVideo", images=["4", 0], audio=["2", 1], fps=["2", 2], bit_depth=8),
        "6": _node("SaveVideo", video=["5", 0], filename_prefix=filename_prefix, format="mp4", codec="auto"),
    }
    return UpscaleWorkflow(
        prompt=graph,
        output_node_id="6",
        model_files=tuple(item.filename for item in UPSCALER_MANIFEST.family_files("flashvsr")),
        required_node_classes=frozenset(node["class_type"] for node in graph.values()),
        provider_id="flashvsr",
    )


def build_seedvr2_workflow(
    input_file: str,
    filename_prefix: str,
    seed: int,
    content_width: int,
    content_height: int,
    *,
    split_latent: bool = True,
) -> UpscaleWorkflow:
    files = {item.id: item.filename for item in UPSCALER_MANIFEST.family_files("seedvr2")}
    graph = {
        "1": _node("LoadVideo", file=input_file),
        "2": _node("GetVideoComponents", video=["1", 0]),
        "3": _node(
            "ImageScale",
            image=["2", 0],
            upscale_method="lanczos",
            width=content_width,
            height=content_height,
            crop="disabled",
        ),
        "4": _node("SeedVR2Preprocess", resized_images=["3", 0]),
        "5": _node("VAELoader", vae_name=files["seedvr2_vae"]),
        "6": _node("UNETLoader", unet_name=files["seedvr2_diffusion"], weight_dtype="default"),
        "7": _node(
            "VAEEncodeTiled",
            pixels=["4", 0],
            vae=["5", 0],
            tile_size=512,
            overlap=128,
            temporal_size=64,
            temporal_overlap=8,
        ),
    }
    latent: list[Any] = ["7", 0]
    if split_latent:
        graph["8"] = _node("SeedVR2TemporalChunk", latent=["7", 0], temporal_overlap=1, chunking_mode="auto")
        latent = ["8", 0]
    graph.update(
        {
            "9": _node("SeedVR2Conditioning", model=["6", 0], vae_conditioning=latent),
            "10": _node(
                "KSampler",
                model=["6", 0],
                positive=["9", 0],
                negative=["9", 1],
                latent_image=latent,
                seed=seed,
                steps=1,
                cfg=1.0,
                sampler_name="euler",
                scheduler="simple",
                denoise=1.0,
            ),
        }
    )
    decoded_latent: list[Any] = ["10", 0]
    if split_latent:
        graph["11"] = _node("SeedVR2TemporalMerge", latents=["10", 0], temporal_overlap=["8", 1])
        decoded_latent = ["11", 0]
    graph.update(
        {
            "12": _node(
                "VAEDecodeTiled",
                samples=decoded_latent,
                vae=["5", 0],
                tile_size=512,
                overlap=128,
                temporal_size=64,
                temporal_overlap=8,
            ),
            "13": _node(
                "SeedVR2PostProcessing",
                images=["12", 0],
                original_resized_images=["3", 0],
                color_correction_method="none",
            ),
            "14": _node("CreateVideo", images=["13", 0], audio=["2", 1], fps=["2", 2], bit_depth=8),
            "15": _node("SaveVideo", video=["14", 0], filename_prefix=filename_prefix, format="mp4", codec="auto"),
        }
    )
    return UpscaleWorkflow(
        prompt=graph,
        output_node_id="15",
        model_files=tuple(item.filename for item in UPSCALER_MANIFEST.family_files("seedvr2")),
        required_node_classes=frozenset(node["class_type"] for node in graph.values()),
        provider_id="seedvr2",
    )
