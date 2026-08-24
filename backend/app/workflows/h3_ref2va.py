from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.h3_manifest import H3_MANIFEST
from app.services.h3_parameters import normalize_h3_parameters
from app.services.references import validate_reference_limits
from app.workflows.h3_t2v import H3Workflow, _node


ROLE_LABELS = {
    "character": "character identity",
    "style": "visual style",
    "motion": "motion",
    "camera": "camera movement",
    "voice": "voice and vocal character",
    "environment": "scene and environment",
    "product": "product identity",
    "general": "general reference",
    "first_frame": "opening frame",
    "last_frame": "ending frame",
}


@dataclass(frozen=True)
class Ref2VAPrompt:
    text: str
    reference_map: tuple[dict[str, Any], ...]


class H3Ref2VAWorkflowAdapter:
    """Isolates the official native ComfyUI Ref2VA API graph from application code."""

    def build(self, parameters: dict[str, object]) -> H3Workflow:
        values = normalize_h3_parameters(parameters)
        references = sorted(
            [dict(item) for item in parameters.get("references", [])],
            key=lambda item: int(item.get("order", 0)),
        )
        validate_reference_limits(references)
        if not references:
            raise ValueError("Reference-to-Video needs at least one reference.")
        files = {item.id: item.filename for item in H3_MANIFEST.files}
        turbo = bool(values.get("turbo", False))
        audio_enabled = bool(values.get("audio_enabled", True))
        steps = 4 if turbo else int(values.get("steps", 20))
        prompt = self.derive_prompt(str(values.get("prompt", "")), references)

        graph: dict[str, dict[str, Any]] = {
            "1": _node("UNETLoader", unet_name=files["ref2va_diffusion"], weight_dtype="default"),
            "2": _node("CLIPLoader", clip_name=files["text_encoder"], type="minimax", device="default"),
            "3": _node("VAELoader", vae_name=files["video_vae"]),
            "4": _node("VAELoader", vae_name=files["audio_vae"]),
            "5": _node(
                "MiniMaxH3ReferenceToVideo",
                clip=["2", 0],
                vae=["3", 0],
                audio_vae=["4", 0],
                prompt=prompt.text,
                width=int(values["width"]),
                height=int(values["height"]),
                length=int(values["frame_count"]),
                ref_image_size=str(parameters.get("ref_image_size", "match")),
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
        if turbo:
            graph["10"] = _node(
                "LoraLoaderModelOnly",
                model=["1", 0],
                lora_name=files["ref2va_turbo_lora"],
                strength_model=1.0,
            )

        next_node = 20
        images = [item for item in references if item["media_type"] == "image"]
        videos = [item for item in references if item["media_type"] == "video"]
        audios = [item for item in references if item["media_type"] == "audio"]
        for index, reference in enumerate(images):
            node_id = str(next_node)
            next_node += 1
            graph[node_id] = _node("LoadImage", image=reference["comfyui_path"])
            graph["5"]["inputs"][f"ref_images.ref_image_{index}"] = [node_id, 0]
        for index, reference in enumerate(videos):
            load_id, parts_id = str(next_node), str(next_node + 1)
            next_node += 2
            graph[load_id] = _node("LoadVideo", file=reference["comfyui_path"])
            graph[parts_id] = _node("GetVideoComponents", video=[load_id, 0])
            graph["5"]["inputs"][f"ref_videos.ref_video_{index}"] = [parts_id, 0]
            if reference.get("audio_present"):
                graph["5"]["inputs"][f"ref_video_audios.ref_video_audio_{index}"] = [parts_id, 1]
        for index, reference in enumerate(audios):
            node_id = str(next_node)
            next_node += 1
            graph[node_id] = _node("LoadAudio", audio=reference["comfyui_path"])
            graph["5"]["inputs"][f"ref_audios.ref_audio_{index}"] = [node_id, 0]

        create_video_inputs: dict[str, Any] = {
            "images": ["12", 0], "fps": 24.0, "bit_depth": 8, "color_space": "sRGB"
        }
        if audio_enabled:
            graph["13"] = _node("VAEDecodeAudio", samples=["11", 0], vae=["4", 0])
            create_video_inputs["audio"] = ["13", 0]
        graph["14"] = _node("CreateVideo", **create_video_inputs)
        graph["15"] = _node(
            "SaveVideo",
            video=["14", 0],
            filename_prefix=f"H3LocalStudio/{values.get('generation_id', 'h3-ref2va')}",
            format="mp4",
            codec="auto",
        )

        model_files = [
            files["ref2va_diffusion"], files["text_encoder"], files["video_vae"], files["audio_vae"]
        ]
        if turbo:
            model_files.append(files["ref2va_turbo_lora"])
        return H3Workflow(
            prompt=graph,
            output_node_id="15",
            width=int(values["width"]),
            height=int(values["height"]),
            frame_count=int(values["frame_count"]),
            steps=steps,
            model_files=tuple(model_files),
            required_node_classes=frozenset(node["class_type"] for node in graph.values()),
            metadata={
                "derived_prompt": prompt.text,
                "reference_map": list(prompt.reference_map),
                "native_reference_order": "images, video soundtrack+video pairs, standalone audio",
                "ref_image_size": graph["5"]["inputs"]["ref_image_size"],
            },
        )

    @staticmethod
    def derive_prompt(user_prompt: str, references: list[dict[str, Any]]) -> Ref2VAPrompt:
        images = [item for item in references if item["media_type"] == "image"]
        videos = [item for item in references if item["media_type"] == "video"]
        audios = [item for item in references if item["media_type"] == "audio"]
        tags: dict[str, str] = {}
        for index, item in enumerate(images, 1):
            tags[str(item.get("asset_id") or item.get("id"))] = f"<Picture {index}>"
        audio_index = 0
        for index, item in enumerate(videos, 1):
            video_tag = f"<Video {index}>"
            if item.get("audio_present"):
                audio_index += 1
                video_tag = f"<Audio {audio_index}> + {video_tag}"
            tags[str(item.get("asset_id") or item.get("id"))] = video_tag
        for item in audios:
            audio_index += 1
            tags[str(item.get("asset_id") or item.get("id"))] = f"<Audio {audio_index}>"

        mapping: list[dict[str, Any]] = []
        lines = ["Reference guide (in the user's chosen order):"]
        for order, item in enumerate(references, 1):
            asset_id = str(item.get("asset_id") or item.get("id"))
            tag = tags[asset_id]
            role = str(item.get("role") or "general")
            note = str(item.get("notes") or "").strip()
            guidance = ROLE_LABELS.get(role, "general reference")
            line = f"{order}. {tag}: use as {guidance}."
            if note:
                line += f" Note: {note}"
            lines.append(line)
            mapping.append(
                {
                    "order": order - 1,
                    "asset_id": asset_id,
                    "filename": item.get("filename"),
                    "media_type": item["media_type"],
                    "role": role,
                    "native_tag": tag,
                }
            )
        lines.extend(["", "Target video description:", user_prompt.strip()])
        return Ref2VAPrompt("\n".join(lines), tuple(mapping))
