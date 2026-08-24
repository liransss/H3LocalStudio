# MiniMax H3

Phase 4 implements real **Text-to-Video and first/last-frame Image-to-Video through FL2VA**, plus **multimodal Reference-to-Video through Ref2VA**, using native ComfyUI nodes and the official [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) files.

Manifest version: `2026.08.24-ref2va.1`  
Canonical workflow sources: `video_minimax_h3_t2v.json` and `video_minimax_h3_r2v.json` in `Comfy-Org/workflow_templates`  
Pinned workflow revision: `0e0f4577453136eaa1c0e9d4b700e3e5ce5bb416`

## FL2VA files

| Role | Standard directory | Exact filename | Size | SHA-256 |
|---|---|---|---:|---|
| Diffusion | `models\diffusion_models` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20,970,379,616 B | `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a` |
| Text encoder | `models\text_encoders` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15,687,142,551 B | `35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6` |
| Video VAE | `models\vae` | `minimax_h3_video_vae_fp16.safetensors` | 5,207,808,496 B | `7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522` |
| Audio VAE | `models\vae` | `minimax_h3_audio_vae_fp32.safetensors` | 605,254,808 B | `8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48` |
| Turbo LoRA | `models\loras` | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1,956,193,000 B | `2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e` |

Total: **44,426,778,471 bytes (~41.37 GiB)**. The installer checks free disk space plus a 2 GiB reserve.

The first four artifacts are pinned to Hugging Face revision `3f57e8291d2ef846f9a074b1b76d2767db434abe`; the FL2VA Turbo LoRA is pinned to `186455f4c2a878eb57d5c7916c5b0f71a77e8ceb`.

## Ref2VA additions

Ref2VA shares the text encoder and both VAEs, then uses:

| Role | Directory | Exact filename | Size | SHA-256 |
|---|---|---|---:|---|
| Diffusion | `models\diffusion_models` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 20,970,379,616 B | `9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779` |
| Turbo LoRA | `models\loras` | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 1,956,193,000 B | `5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c` |

Ref2VA totals **44,426,778,471 bytes (~41.37 GiB)**. Its text encoder and both VAEs are shared with FL2VA (21,500,205,855 bytes); only the Ref2VA diffusion model and Turbo LoRA are new downloads (22,926,572,616 bytes, ~21.35 GiB). The model manager labels shared components and will not start concurrent family operations that could duplicate a large download.

The Ref2VA diffusion file is pinned to revision `3f57e8291d2ef846f9a074b1b76d2767db434abe`; the Ref2VA Turbo LoRA is pinned to `edc77b088b1cb17f00cc1a57f68f263e82f9cc1d`.

## Reference inputs and routing

The project media library accepts PNG/JPG/JPEG/WEBP images, MP4/MOV/WEBM/MKV video, and WAV/MP3/M4A/FLAC audio. Uploads are validated with FFprobe/FFmpeg before persistence and deduplicated by SHA-256. Timed references must be 2-15 seconds.

Reference limits follow the native node contract: at most 9 images, 3 videos, 3 standalone audio clips, and 12 combined assets. Each item may have an optional Character, Style, Motion, Camera, Voice, Environment, Product, First frame, Last frame, or General role plus a note. The final order, roles, notes, durations, hashes, and asset IDs are snapshotted into every generation.

Auto routing is deterministic:

- no references -> T2V / FL2VA;
- one or two images explicitly assigned First frame / Last frame -> I2V / FL2VA;
- general images, video, audio, or mixed references -> R2V / Ref2VA.

The user's prompt is never creatively rewritten. Ref2VA prepends a stored, deterministic reference guide containing role, note, and native tag mappings, then appends the user's target-video description unchanged.

The native node accepts namespaced dynamic inputs (`ref_images.ref_image_N`, `ref_videos.ref_video_N`, `ref_video_audios.ref_video_audio_N`, and `ref_audios.ref_audio_N`). Native presentation groups images first, paired video audio/video next, and standalone audio last. The app preserves the user's global order in its snapshot and prompt guide, and preserves order within every native type group; this native cross-type grouping is documented rather than hidden.

## Installation and verification

The Models page shows Missing, Partial, Invalid, Installed, or Verified for every component. Install/Repair requires a confirmation dialog listing files, total estimated size, and target directory.

- HTTP Range is used to resume an existing `.part` file when the source supports it.
- The final name never appears until byte size and SHA-256 match.
- Atomic rename completes installation.
- Cancellation keeps the visible `.part` file for resume.
- Invalid full files/downloads are preserved with `.invalid-<timestamp>` for diagnosis/repair.
- A successful verification cache is tied to manifest version, size, and file modification time.

## Resolution mapping

H3 output is 768p-class. Width and height are derived from the official template’s target megapixel policy, then rounded to multiples of 32.

| Aspect | Preview | High |
|---|---:|---:|
| 16:9 | 736×416 | 1344×768 |
| 9:16 | 416×736 | 768×1344 |
| 1:1 | 576×576 | 1024×1024 |
| 4:3 | 640×480 | 1184×864 |
| 3:4 | 480×640 | 864×1184 |
| 21:9 | 864×352 | 1536×672 |

Local GPU Mode always stores the native result as `original`. It does not generate 1920×1080 and does not call the Phase 1 resize path. AI upscale is Phase 3.

## Duration and frames

Native FPS is always 24. Accepted duration is 4–15 seconds. Requested frames are rounded from seconds×24, then snapped upward to H3’s native `17k+5` temporal grid:

```text
frames = requested + ((5 - requested mod 17) mod 17)
```

Examples: 4 s → 107 frames, 5 s → 124, 8 s → 192, 10 s → 243, 15 s → 362. The actual encoded duration is read back from FFprobe rather than assumed.

## Prompt, seed, Turbo, and audio

- Multiline Unicode prompt text is inserted only into `MiniMaxH3ImageToVideo.prompt`.
- Manual or random seed is inserted into `RandomNoise.noise_seed` and persisted in SQLite/metadata.
- Quality uses the requested step count (20 by default) without a LoRA.
- Turbo is explicit. FL2VA loads the official 8-step LoRA; Ref2VA loads the official 4-step LoRA. Both use strength 1.0 and force the matching step count.
- Native audio is decoded from the joint latent with the official audio VAE and muxed by `CreateVideo`/`SaveVideo`.
- FFprobe stores `audio_present`, codec, sample rate, and channels. If audio was requested but absent, the generation fails instead of silently claiming success.

Stored execution data includes prompt, exact seed, requested duration, actual width/height/FPS/duration, workflow family, model filenames, manifest version, ComfyUI prompt ID, execution seconds, media codecs, and output path.

## Completed hardware results

The FL2VA conservative preview-then-native sequence passed on the target RTX 5070 Ti. Preview completed at 736×416 in 56.658 seconds with 15,279 MiB peak VRAM. Native High completed at 1344×768 in 219.426 seconds with 13,822 MiB peak VRAM.

Four real Ref2VA preview runs also passed: two images (49.279 s), image plus video/soundtrack (143.787 s), image plus standalone audio (45.860 s), and two images plus video/soundtrack plus standalone audio (165.737 s). All produced 736×416, 24 fps, 4.458333-second H.264/AAC files. Peak Ref2VA VRAM was 15.14 GiB and minimum available system RAM was 1.57 GiB, confirming that 32 GB system RAM is the practical constraint. The two-image result also passed the unchanged Phase 3 SeedVR2 pipeline at 1920×1080.

Full telemetry and reliability evidence are in [`VALIDATION.md`](VALIDATION.md) and [`runtime-manifest.json`](runtime-manifest.json).

## Reproduction recipe

First Ref2VA run:

```text
Mode: Auto or Reference to Video
References: one or two images with optional Character / Environment roles
Quality: Preview (736×416 for 16:9)
Duration: 4 seconds
Turbo: enabled
Audio: enabled
Prompt: A concise description of the intended shot, motion, camera, and sound.
```

After model load, output retrieval, playback, audio, History, and exact seed/reference persistence pass, add one short video or audio reference. Run large mixed sets only after preview succeeds, and close memory-intensive applications first.
