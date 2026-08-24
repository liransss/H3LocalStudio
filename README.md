# H3 Local Studio

H3 Local Studio is a local-first Windows desktop interface for MiniMax H3 video generation through native ComfyUI. Prompts, model files, generated media, logs, and SQLite history remain on the user’s PC.

Version **0.1.0** contains the Phase 4 local-inference implementation. It has passed real FL2VA and multimodal Ref2VA generation, plus production FlashVSR Fast 1080p and SeedVR2 Best Quality 1080p upscaling, on the target RTX 5070 Ti workstation. The application never starts a multi-gigabyte model download without explicit confirmation.

## Current capabilities

- React/Tauri interface with Create, result playback, History, Projects, Models, Settings, and a clearly marked Spaces preview
- FastAPI control layer bound to localhost, SQLite migrations, a serial GPU queue, WebSocket job updates, and cancellation
- Strictly separated Mock Mode and Local GPU Mode—real failures never fall back to fake output
- Managed or external ComfyUI, native H3 version/node preflight, managed background launch/logging, start/stop, and opt-in update
- Canonical queueable T2V and Ref2VA API graphs based on the official Comfy-Org workflows and native MiniMax H3 nodes
- Real `/prompt` submission, ComfyUI WebSocket progress, `/interrupt`, history-based output discovery, and output import
- Pinned Comfy-Org model manifest with standard directories, exact sizes/SHA-256 values, resumable `.part` downloads, disk preflight, cancellation, verification, and repair
- Native 24 fps H3 duration/frame alignment, official resolution mapping, optional native audio, and the official FL2VA 8-step / Ref2VA 4-step Turbo LoRAs
- Reusable, SHA-256-deduplicated project reference media with image/video/audio validation, previews, roles, notes, ordering, and generation snapshots
- Auto routing: no references uses T2V; one or two explicitly marked frame images use I2V/FL2VA; general image, video, audio, or mixed references use Ref2VA
- Official limits enforced before queueing: 9 images, 3 videos, 3 audio clips, and 12 total; timed references must be 2-15 seconds
- Pinned FlashVSR v1.1 (SDPA, tiled/offloaded Fast profile) and native ComfyUI SeedVR2 3B INT8 (one-step, automatic temporal chunks)
- Independent Original, Fast 1080p, and Best Quality 1080p variants with exact filenames, provider metadata, resource telemetry, retries, and failure-safe original retention
- FFprobe validation of video dimensions, FPS, duration, codec, and audio metadata before a result enters History
- 45 non-GPU backend tests covering Phase 1 through Phase 4 contracts, including Ref2VA routing, graph injection, persistence, failures, and cancellation

T2V, first/last-frame I2V, and multimodal Ref2VA are real local generation modes. 4K output, frame interpolation, interactive Spaces, and named reference-set presets are intentionally deferred; project media already provides reusable, deduplicated assets.

## Development setup

Prerequisites: Windows 11, Python 3.11+, Node.js 20+, and FFmpeg/FFprobe on `PATH` (or an FFmpeg path in Settings).

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
npm.cmd run dev
```

`npm.cmd run dev` uses explicit Mock Mode and opens the UI at <http://127.0.0.1:1420>. Run Local GPU Mode with:

```powershell
npm.cmd run backend:prod
npm.cmd run frontend:dev
```

PowerShell may block `npm.ps1`; `npm.cmd` avoids changing machine-wide execution policy.

## Local GPU quick start

1. Install current ComfyUI **0.30.0 or newer** using its official Windows instructions or portable build.
2. In Settings, choose **Managed** and set the ComfyUI path, or choose **External** and configure its localhost host/port.
3. Open Models, choose **MiniMax H3 FL2VA** or **MiniMax H3 Ref2VA**, review the files, shared components, target, and exact missing bytes, then explicitly confirm **Install missing**.
4. Verify the selected model stack. Start ComfyUI from Settings in Managed mode, or start the external instance yourself.
5. For Ref2VA, add images, short videos, and/or audio in Reference Media, optionally assign roles and notes, then arrange them in the intended order. Start with Preview, 4 seconds, and one or two references on a 32 GB machine.
6. Create a generation. Preview maps 16:9 to 736×416; High maps it to native 1344×768.
7. Optionally install **FlashVSR Fast** (6,948,393,553 bytes) or **SeedVR2 Best Quality** (3,959,584,518 bytes) from Models after reviewing the confirmation dialog, then select a 1080p variant in Create or Result.

Managed Balanced launch:

```text
<ComfyUI Python> main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
```

Low VRAM adds the official `--lowvram` flag. H3 Local Studio does not silently install or replace PyTorch/CUDA. For an RTX 5070 Ti, use a current official ComfyUI portable/runtime build that supports Blackwell; see [ComfyUI setup](docs/COMFYUI.md).

## Storage

The default data root is `F:\AI\H3LocalStudio` when `F:` exists, otherwise `%LOCALAPPDATA%\H3LocalStudio`. Managed ComfyUI defaults to `<data-root>\runtime\ComfyUI`; a configured path always wins.

```text
H3LocalStudio\
├── outputs\YYYY\MM\project-id\generation-id\
├── inputs\references\sha-prefix\
├── cache\
├── logs\backend.log
├── logs\comfyui.log
├── database\studio.db
└── runtime\ComfyUI\models\
    ├── diffusion_models\
    ├── text_encoders\
    ├── vae\
    ├── loras\
    └── FlashVSR-v1.1\
```

Models, outputs, databases, caches, runtime environments, and logs are excluded from Git.

## Quality checks

```powershell
backend\.venv\Scripts\python.exe -m pytest
npm.cmd exec tsc -- -b --pretty false
npm.cmd run build
```

Automated tests mock ComfyUI and do not download models or require a GPU. Real FL2VA/Ref2VA validation is separate because the model stacks are very large.

## API

OpenAPI is at <http://127.0.0.1:7331/api/docs>. Important routes include:

- `POST /api/generations`, `GET /api/generations/{id}`
- `POST /api/projects/{id}/references`, `GET /api/projects/{id}/references`
- `GET /api/reference-assets/{id}/content|preview`
- `POST /api/generations/{id}/upscale`, `GET /api/media/{id}/{original|flashvsr|seedvr2}`
- `POST /api/jobs/{id}/cancel`, `WS /api/jobs/{id}/ws`
- `GET /api/models`, `POST /api/models/install`, `POST /api/models/verify`
- `GET /api/models/operations/{id}`, `POST /api/models/operations/{id}/cancel`
- `GET /api/comfyui/health`, `POST /api/comfyui/start|stop|update`
- `GET /api/system/status`, `GET|PATCH /api/settings`

## Documentation

- [ComfyUI setup, ownership modes, launch, and troubleshooting](docs/COMFYUI.md)
- [MiniMax H3 model manifest and workflow behavior](docs/MINIMAX_H3.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Windows development](docs/DEVELOPMENT.md)
- [Real GPU validation and measured performance](docs/VALIDATION.md)
- [Pinned runtime/model/result manifest](docs/runtime-manifest.json)
- [Exact validated ComfyUI Python package lock](docs/comfyui-requirements-lock.txt)

Canonical upstream sources are the official [ComfyUI repository](https://github.com/comfyanonymous/ComfyUI), [Comfy-Org workflow templates](https://github.com/Comfy-Org/workflow_templates), and [Comfy-Org MiniMax-H3 repository](https://huggingface.co/Comfy-Org/MiniMax-H3).

## Known limitations

- Real GPU inference is intentionally separate from automated tests because each H3 family occupies 44,426,778,471 bytes including shared artifacts.
- The native Ref2VA node presents references in type groups (images, then video soundtrack/video pairs, then standalone audio). H3 Local Studio preserves the user's global order in metadata and role guidance and preserves order within each native type group.
- Reference-to-Video is practical but memory-constrained on 32 GB RAM. Preview-first, short-duration runs with one or two references are the safest default.
- AI upscaling is intentionally limited to 1080p in Phase 3. The original H3 MP4 is immutable and remains playable if an upscale is cancelled or fails.
- Audio-enabled runs fail validation if ComfyUI produces no audio stream. This makes upstream audio regressions visible instead of silently accepting a video-only file.
- Managed update supports clean Git checkouts and uses `git pull --ff-only`; it does not modify external installations or resolve local changes.
- The app does not install GPU drivers, CUDA, PyTorch, or ComfyUI dependencies automatically.
