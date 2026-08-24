# ComfyUI integration

H3 Local Studio uses current native ComfyUI MiniMax H3 support. The minimum accepted version is **0.30.0**. The adapter was audited against official ComfyUI `v0.33.1` source and the official workflow template revision `0e0f4577453136eaa1c0e9d4b700e3e5ce5bb416` (2026-08-18).

## Ownership modes

**Managed** means H3 Local Studio may start and stop the configured ComfyUI process. Auto-start is optional. Stdout/stderr is appended to `<data-root>\logs\comfyui.log`. The Update action only runs on a clean Git checkout, uses `git pull --ff-only`, and requires an explicit click.

**External** means the user owns the process and files. H3 Local Studio performs localhost health/API calls and may download models only after the user explicitly confirms a Models action. It never starts, stops, or updates external ComfyUI.

Both API and ComfyUI hosts are restricted to loopback addresses.

## Managed launch profiles

Balanced is the default for the target RTX 5070 Ti 16 GB system:

```text
<python> <ComfyUI>\main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
```

Low VRAM appends only the official flag:

```text
--lowvram
```

The launcher finds Python in this order:

1. `<ComfyUI>\.venv\Scripts\python.exe`
2. `<ComfyUI>\venv\Scripts\python.exe`
3. the sibling `python_embeded\python.exe` used by ComfyUI Portable
4. the backend’s current Python executable

If the last fallback lacks ComfyUI dependencies, startup exits and the UI points to `comfyui.log`; it does not mutate that environment.

## PyTorch, CUDA, and Blackwell

H3 Local Studio deliberately does not pin or replace an existing PyTorch/CUDA installation. As of the audited current official ComfyUI README, NVIDIA’s stable instructions use the CUDA 13.0 (`cu130`) PyTorch index and current Portable builds bundle Python 3.13 with PyTorch CUDA 13.0. The official note requires cu130 or newer for NVIDIA 20-series and newer GPUs, which includes RTX 50-series Blackwell.

Use the current official [ComfyUI installation instructions](https://github.com/comfyanonymous/ComfyUI#installing) and verify compatibility with the installed NVIDIA driver. Prefer the official Portable build for an isolated Windows runtime. Do not blindly reinstall torch in a working ComfyUI environment.

## Validated target runtime

The validated installation is pinned in [`runtime-manifest.json`](runtime-manifest.json): ComfyUI `v0.33.1` at commit `72865f4f27eaf5396f8f36370e0a2be3a9a090ee`, Python 3.12.10, Torch 2.12.1 + cu130, torchvision 0.27.1, and torchaudio 2.11.0. On the target machine Smart App Control required SciPy 1.16.3 and PyAV 16.0.1; the Windows security policy was not disabled.

## Preflight and API execution

Before a real job is queued to ComfyUI, the backend:

1. resolves T2V/I2V to FL2VA and general/multimodal R2V to Ref2VA, then verifies that every required family file exists at its exact expected size;
2. starts managed ComfyUI if necessary, or requires the external instance to be online;
3. reads `/system_stats` and rejects versions older than 0.30.0;
4. reads `/object_info` and verifies every required native node class;
5. builds an isolated canonical API-format graph in `backend/app/workflows/h3_t2v.py` or `backend/app/workflows/h3_ref2va.py`;
6. opens `/ws?clientId=...` before posting `{prompt, client_id}` to `/prompt`;
7. maps real `executing` and `progress` events to the existing job stream;
8. reads `/history/{prompt_id}`, selects the actual `SaveVideo` artifact, and downloads it through `/view`;
9. validates the imported MP4 with FFprobe.

Raw ComfyUI node IDs are isolated in the workflow adapter and never reach React or public generation parameters. The official UI template itself is not posted to `/prompt` because UI workflow JSON is not the same contract as queueable API prompt JSON.

Cancellation marks the H3 Local Studio job cancelled and calls ComfyUI `/interrupt`. A cancelled import cannot be marked completed by a late progress update.

Ref2VA assets are validated when uploaded, then copied into unique per-job paths beneath ComfyUI's `input` directory. The provider removes that staging directory on success, failure, or cancellation. Before queueing, it unloads ComfyUI models, checks live RAM/VRAM, warns for large reference sets, and records one-second resource telemetry. Generation and later upscaling remain separate serialized jobs so their model families are never intentionally resident together.

Managed ComfyUI is launched with UTF-8 Python I/O (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`). This is required on Windows because FlashVSR emits Unicode progress text and a CP1252 child process can otherwise terminate the ComfyUI prompt worker while logging.

## Phase 3 upscaler nodes

FlashVSR uses the pinned `ComfyUI-FlashVSR_Stable` custom node at commit `f7f55bae4c0e82b18b190d4b62a977995507c51c` with `triton-windows 3.7.1.post27`. The production graph deliberately selects its built-in SDPA path; SageAttention and FlashAttention are not required. Managed setup may install this exact node/dependency, but never downgrades or replaces PyTorch.

SeedVR2 uses current native ComfyUI nodes (`SeedVR2Preprocess`, `SeedVR2TemporalChunk`, `SeedVR2Conditioning`, `SeedVR2TemporalMerge`, and `SeedVR2PostProcessing`) plus standard loaders, tiled VAE nodes, `KSampler`, `CreateVideo`, and `SaveVideo`.

Before either run, H3 Local Studio validates the provider's complete node set through `/object_info`, requests `/free` with model unload, checks available system/GPU memory, and then queues the workflow through the same WebSocket execution path as H3.

## Native node set

The T2V graph validates and uses:

```text
UNETLoader, CLIPLoader, VAELoader, LoraLoaderModelOnly (Turbo only),
MiniMaxH3ImageToVideo, RandomNoise, KSamplerSelect, BasicScheduler,
BasicGuider, SamplerCustomAdvanced, VAEDecode, VAEDecodeAudio (audio only),
CreateVideo, SaveVideo
```

Sampler is `res_multistep`; scheduler is `simple`; FPS is 24. Turbo uses the official FL2VA 8-step LoRA at strength 1.0 and exactly 8 steps.

The Ref2VA graph validates and uses:

```text
UNETLoader, CLIPLoader, VAELoader, LoraLoaderModelOnly,
LoadImage, LoadVideo, GetVideoComponents, LoadAudio,
MiniMaxH3ReferenceToVideo, RandomNoise, KSamplerSelect, BasicScheduler,
BasicGuider, SamplerCustomAdvanced, VAEDecode, VAEDecodeAudio,
CreateVideo, SaveVideo
```

Ref2VA Turbo uses the official 4-step LoRA. Dynamic reference inputs use the exact namespaced V3 API keys exposed by `MiniMaxH3ReferenceToVideo`; video soundtrack inputs are paired with their corresponding video inputs. Raw node IDs and socket keys remain backend-only.

## Troubleshooting

**“MiniMax H3 requires ComfyUI 0.30.0 or newer.”**

Update a managed clean Git checkout with Settings → Update ComfyUI, or update an external installation yourself. Restart ComfyUI afterward.

**“Missing nodes” or workflow version mismatch**

Confirm the configured URL points to the expected current ComfyUI instance. Inspect `/object_info` and `logs\comfyui.log`. No unofficial H3 custom node is required.

**ComfyUI exits during startup**

Open `<data-root>\logs\comfyui.log`. Check the selected ComfyUI path, Python environment, torch/CUDA installation, and NVIDIA driver.

**CUDA out of memory**

Close GPU-heavy applications such as Premiere Pro. Switch the managed launch profile to Low VRAM and restart ComfyUI. Use Preview (736×416 at 16:9), 4 seconds, and Turbo for the first diagnostic run.

**Not enough system memory for this reference set**

Ref2VA was measured with as little as 1.57 GiB system RAM free on this 32 GB workstation. Close memory-heavy applications, reduce the reference count, use shorter source clips, and start at Preview. H3 Local Studio warns but never terminates other applications.

**The output has no audio**

Audio-enabled jobs are intentionally rejected by FFprobe if no audio stream exists. Review the ComfyUI log for native H3 audio decode/mux errors. As a diagnostic only, disable Native H3 audio and verify video generation separately.

**External ComfyUI must not be changed**

Select External. Start/update it independently. Model installation still requires an explicit confirmation dialog because it writes to that configured ComfyUI model tree.
