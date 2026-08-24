# Real Phase 2, Phase 3, and Phase 4 validation

FL2VA generation, both AI upscalers, and multimodal Ref2VA were validated on 2026-08-24 on the target Windows workstation, not only against mocks. Exact machine, runtime, provider, and model facts are machine-readable in [`runtime-manifest.json`](runtime-manifest.json).

## Installed runtime

- ComfyUI `v0.33.1`, commit `72865f4f27eaf5396f8f36370e0a2be3a9a090ee`
- Python 3.12.10; PyTorch 2.12.1 + CUDA 13.0
- RTX 5070 Ti 16,303 MiB, NVIDIA driver 610.62; 32 GiB system RAM
- FFmpeg/FFprobe 8.1.2
- FL2VA: five files, 44,426,778,471 bytes, all exact SHA-256 values verified
- Ref2VA: five files, 44,426,778,471 bytes, all exact SHA-256 values verified; 21,500,205,855 shared bytes and 22,926,572,616 newly downloaded bytes
- FlashVSR v1.1: four files, 6,948,393,553 bytes, all exact SHA-256 values verified
- SeedVR2 3B INT8: two files, 3,959,584,518 bytes, both exact SHA-256 values verified
- FlashVSR ComfyUI node pinned to commit `f7f55bae4c0e82b18b190d4b62a977995507c51c`; `triton-windows==3.7.1.post27`

Windows Smart App Control remained enabled. Current unpinned SciPy 1.18.1 and PyAV 18.1.0 extensions were blocked by code integrity. Requirement-compatible SciPy 1.16.3 and PyAV 16.0.1 wheels passed imports and runtime execution; these versions are recorded in the lock and manifest.

## Phase 2 generation

| Run | Output | Execution | Peak VRAM | Peak RAM used | Minimum RAM free | Result |
|---|---:|---:|---:|---:|---:|---|
| Preview, 4 s, Turbo/audio | 736×416, 24 fps | 56.658 s | 15,279 MiB | 30,715 MiB | 1,511 MiB | Pass |
| Native, 4 s, Turbo/audio | 1344×768, 24 fps | 219.426 s | 13,822 MiB | 30,886 MiB | 1,340 MiB | Pass |

Both files are 4.458333 seconds and contain H.264 video plus AAC stereo audio at 32 kHz. The native audio stream contains 286,720 samples with −30.9 dB mean and −14.3 dB peak, so it is not an empty or silent placeholder. Representative frames were visually inspected and were coherent with the prompt.

## Phase 3 real upscales

The immutable source was generation `de734bae-0349-436e-8398-6783838402d2`: H.264 1344×768, 24 fps, 107 frames, 4.458333 seconds, with AAC 32 kHz stereo audio. Its SHA-256 is `a69cd582b882568b98d2676fe1d35fc860149bd271f2a97c284b93a3f26df22d`.

| Provider | Final media | App execution | AI provider | Peak VRAM | Peak RAM used | Minimum RAM free | Result |
|---|---|---:|---:|---:|---:|---:|---|
| FlashVSR Fast | 1920×1080, 24 fps, 107 frames, 4.458333 s | 758.399 s | 757.126 s | 10.88 GiB | 27.04 GiB | 4.43 GiB | Pass |
| SeedVR2 Best | 1920×1080, 24 fps, 107 frames, 4.458008 s | 251.996 s | 251.092 s | 14.16 GiB | 30.45 GiB | 1.02 GiB | Pass |

Both outputs are H.264 High, progressive yuv420p, square-pixel 16:9, with the source frame rate and count. Both contain 141 AAC packets at the source 32 kHz stereo format. The encoded audio packet MD5 is `cc2f21aaf49a5f10bff8a44c14852f34` for the original and both variants, proving that the original compressed audio stream was copied without re-encoding.

- FlashVSR output SHA-256: `1955c651f0e4e7af961fdc42f4fcb429b8c9cb89c4e87f78518ca8d7f3b7d0f6`
- SeedVR2 output SHA-256: `98d7081f85619ab97c783f3d8ed4d47e6eb89e47c8b4d7708d9f8f2649fc5bd0`
- FFmpeg decoded every frame in both variants. `freezedetect` (−50 dB, 0.5 s) and `blackdetect` (0.25 s, 2% threshold) reported no events.
- Against a Lanczos resize of the source—not a ground-truth quality target—FlashVSR measured SSIM 0.930558 and PSNR 32.079 dB; SeedVR2 measured SSIM 0.937372 and PSNR 31.970 dB.
- Side-by-side inspection found coherent anatomy and composition with no visible tile seams or structural hallucinations. FlashVSR retained a more restrained color response while sharpening rain, glass, and metal edges. SeedVR2 produced the strongest eye and edge micro-detail, with a warmer, higher-contrast rendering and deeper shadows.

The similarity metrics describe divergence from a conventional resize and must not be read as perceptual ground truth. The visual assessment is therefore recorded separately.

## Phase 4 real Ref2VA generation

Four staged Local GPU Mode tests used the native `MiniMaxH3ReferenceToVideo` graph with the official 4-step Turbo LoRA. No cloud service or mock fallback was active. All outputs are 736×416 H.264 at 24 fps and 4.458333 seconds with AAC 32 kHz stereo audio. Representative frames were visually inspected and remained coherent with the brass-robot/workshop reference set.

| Test | Ordered input set | Generation ID | Execution | Peak VRAM | Peak RAM used | Minimum RAM free | Size | Result |
|---|---|---|---:|---:|---:|---:|---:|---|
| A | 2 images | `33d44b01-86ec-4c04-af85-5d0797900c83` | 49.279 s | 15.05 GiB | 29.52 GiB | 1.95 GiB | 588,230 B | Pass |
| B | image + 3 s video with paired soundtrack | `ff9ea6cc-96cb-465b-a118-12c165c84ed7` | 143.787 s | 15.14 GiB | 29.90 GiB | 1.57 GiB | 642,006 B | Pass |
| C | image + 3 s standalone audio | `e53b6870-8dc6-423d-9d18-72a1a50b5a3f` | 45.860 s | 14.90 GiB | 29.62 GiB | 1.85 GiB | 518,418 B | Pass |
| D | image, video/soundtrack, second image, standalone audio | `5c397862-c44e-4a25-a1b2-fdfc46a6eac4` | 165.737 s | 15.14 GiB | 29.87 GiB | 1.60 GiB | 573,302 B | Pass |

Output paths:

```text
F:\AI\H3LocalStudio\outputs\2026\08\5802a882-900a-415e-b176-fbd5ccb0e3e4\33d44b01-86ec-4c04-af85-5d0797900c83\33d44b01-86ec-4c04-af85-5d0797900c83_original.mp4
F:\AI\H3LocalStudio\outputs\2026\08\5802a882-900a-415e-b176-fbd5ccb0e3e4\ff9ea6cc-96cb-465b-a118-12c165c84ed7\ff9ea6cc-96cb-465b-a118-12c165c84ed7_original.mp4
F:\AI\H3LocalStudio\outputs\2026\08\5802a882-900a-415e-b176-fbd5ccb0e3e4\e53b6870-8dc6-423d-9d18-72a1a50b5a3f\e53b6870-8dc6-423d-9d18-72a1a50b5a3f_original.mp4
F:\AI\H3LocalStudio\outputs\2026\08\5802a882-900a-415e-b176-fbd5ccb0e3e4\5c397862-c44e-4a25-a1b2-fdfc46a6eac4\5c397862-c44e-4a25-a1b2-fdfc46a6eac4_original.mp4
```

Test D persisted the exact user order as Character image, Motion video, Environment image, Voice audio. Its native mapping correctly became `Picture 1`, `Audio 1 + Video 1`, `Picture 2`, and `Audio 2`; the deterministic derived prompt and the global snapshot preserve the user's intended cross-type order even though the native ComfyUI node presents sockets in type groups.

The Test A original then entered the existing SeedVR2 provider without modification. It produced a separate 7,724,593-byte 1920×1080 H.264/AAC variant in 249.408 seconds (provider 248.151 s), with 13.19 GiB peak VRAM, 25.12 GiB peak RAM used, and 6.35 GiB minimum RAM free. The original SHA-256 is `8ddcfc80af45cb69d4c16660094c5104ebc6224f16fb77b3fc9b949e67b8e085`; the independent SeedVR2 variant is `93fc86668eba672486f4862721a89d4d1976e4880343e3473382791cb0c97998`.

```text
F:\AI\H3LocalStudio\outputs\2026\08\5802a882-900a-415e-b176-fbd5ccb0e3e4\33d44b01-86ec-4c04-af85-5d0797900c83\33d44b01-86ec-4c04-af85-5d0797900c83_1080p_seedvr2.mp4
```

## Phase 4 cancellation and recovery

- Generation `59514923-c765-4b1d-ae63-3dfcbc24515e` / job `245e1b74-164c-4b60-a10e-77975ef2e0bd` was interrupted at the Generating video boundary. Both records reached `cancelled`, no output was imported, ComfyUI reported zero running/pending prompts, and the per-job input staging directory was removed.
- The immediately following Ref2VA generation `5fd7fa3f-a3dc-4b5b-baee-07864c032f41` completed in 44.779 seconds with audio, proving that cancellation left the queue and provider reusable.
- A mixed four-reference run surfaced the intended RAM-pressure warning. No OOM occurred, but the 1.57 GiB minimum free RAM observed in Test B supports Preview, 4 seconds, and one or two references as the default operating recommendation on 32 GB RAM.

## Reliability

- The preflight memory guard unloads ComfyUI models, queries live RAM and VRAM, and blocks unsafe starts. Runtime telemetry samples RAM, VRAM, GPU utilization, and process state through the job.
- A real FlashVSR job was cancelled while active. The ComfyUI queue was interrupted, the job gained a terminal timestamp, the generation returned to `completed` with `Original ready`, and the original file remained playable and hash-identical.
- A FlashVSR provider log containing Unicode exposed a Windows CP1252 worker crash. Managed ComfyUI now launches with UTF-8 mode and the same real pipeline completes.
- FlashVSR emitted fewer frames than the source through its native workflow. The finalizer now clone-pads or trims the AI stream to the exact source duration and frame count, scales to 1920×1080 without distortion, copies source audio, and rejects invalid final media.
- Managed Phase 2 stop/start closed all local ports and returned ComfyUI healthy in 10.18 seconds. An active generation cancelled at 20%, cleared the ComfyUI queues, and a new preview immediately completed in 48.553 seconds.
- Browser verification traced Home/History → generation API → persisted variants → byte-range media responses. Original rendered at 1344×768, then the selector loaded the FlashVSR and SeedVR2 endpoints at 1920×1080; all API/media requests returned HTTP 200/206, with no page error, Vite overlay, or console error.
- Phase 4 browser verification uploaded each supported media type, rendered image/video/audio cards and durations, edited roles/notes, changed order, displayed project asset counts, reopened Ref2VA History results with all reference metadata, and selected the generated SeedVR2 variant. The responsive result dialog was checked at 1264×768.

Phase 4 intentionally does not implement 4K output, frame interpolation, denoising, deblocking, third-party deployment, batch conversion, interactive Spaces, or named reference-set presets.
