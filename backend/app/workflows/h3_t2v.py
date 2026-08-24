from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.h3_manifest import H3_MANIFEST
from app.services.h3_parameters import normalize_h3_parameters


@dataclass(frozen=True)
class H3Workflow:
    prompt: dict[str, dict[str, Any]]
    output_node_id: str
    width: int
    height: int
    frame_count: int
    steps: int
    model_files: tuple[str, ...]
    required_node_classes: frozenset[str]
    metadata: dict[str, Any] | None = None


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def build_h3_t2v_workflow(parameters: dict[str, object]) -> H3Workflow:
    values = normalize_h3_parameters(parameters)
    files = {item.id: item.filename for item in H3_MANIFEST.files}
    turbo = bool(values.get("turbo", False))
    audio_enabled = bool(values.get("audio_enabled", True))
    steps = 8 if turbo else int(values.get("steps", 20))

    graph: dict[str, dict[str, Any]] = {
        "1": _node("UNETLoader", unet_name=files["fl2va_diffusion"], weight_dtype="default"),
        "2": _node("CLIPLoader", clip_name=files["text_encoder"], type="minimax", device="default"),
        "3": _node("VAELoader", vae_name=files["video_vae"]),
        "4": _node("VAELoader", vae_name=files["audio_vae"]),
        "5": _node(
            "MiniMaxH3ImageToVideo",
            clip=["2", 0],
            vae=["3", 0],
            prompt=str(values.get("prompt", "")),
            width=int(values["width"]),
            height=int(values["height"]),
            length=int(values["frame_count"]),
        ),
        "6": _node("RandomNoise", noise_seed=int(values.get("seed", 0))),
        "7": _node("KSamplerSelect", sampler_name="res_multistep"),
        "8": _node("BasicScheduler", model=["10" if turbo else "1", 0], scheduler="simple", steps=steps, denoise=1.0),
        "9": _node("BasicGuider", model=["10" if turbo else "1", 0], conditioning=["5", 0]),
        "11": _node(
            "SamplerCustomAdvanced",
            noise=["6", 0],
            guider=["9", 0],
            sampler=["7", 0],
            sigmas=["8", 0],
            latent_image=["5", 1],
        ),
        "12": _node("VAEDecode", samples=["11", 0], vae=["3", 0]),
    }
    if parameters.get("mode") == "i2v":
        references = sorted(
            [dict(item) for item in parameters.get("references", [])],
            key=lambda item: int(item.get("order", 0)),
        )
        by_role = {item.get("role"): item for item in references}
        first = by_role.get("first_frame") or references[0]
        last = by_role.get("last_frame") or (references[1] if len(references) > 1 else None)
        graph["20"] = _node("LoadImage", image=first["comfyui_path"])
        graph["5"]["inputs"]["first_frame"] = ["20", 0]
        if last and last is not first:
            graph["21"] = _node("LoadImage", image=last["comfyui_path"])
            graph["5"]["inputs"]["last_frame"] = ["21", 0]
    if turbo:
        graph["10"] = _node(
            "LoraLoaderModelOnly",
            model=["1", 0],
            lora_name=files["fl2va_turbo_lora"],
            strength_model=1.0,
        )

    create_video_inputs: dict[str, Any] = {
        "images": ["12", 0],
        "fps": 24.0,
        "bit_depth": 8,
        "color_space": "sRGB",
    }
    if audio_enabled:
        graph["13"] = _node("VAEDecodeAudio", samples=["11", 0], vae=["4", 0])
        create_video_inputs["audio"] = ["13", 0]
    graph["14"] = _node("CreateVideo", **create_video_inputs)
    graph["15"] = _node(
        "SaveVideo",
        video=["14", 0],
        filename_prefix=f"H3LocalStudio/{values.get('generation_id', 'h3')}",
        # ComfyUI 0.33 exposes the container and dynamic codec as separate
        # inputs. Dynamic-combo selections are serialized as their option key;
        # ComfyUI expands that key into the dictionary passed to the node.
        format="mp4",
        codec="auto",
    )

    model_files = [files["fl2va_diffusion"], files["text_encoder"], files["video_vae"], files["audio_vae"]]
    if turbo:
        model_files.append(files["fl2va_turbo_lora"])
    return H3Workflow(
        prompt=graph,
        output_node_id="15",
        width=int(values["width"]),
        height=int(values["height"]),
        frame_count=int(values["frame_count"]),
        steps=steps,
        model_files=tuple(model_files),
        required_node_classes=frozenset(node["class_type"] for node in graph.values()),
    )
