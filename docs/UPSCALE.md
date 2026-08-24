# Upscaling and post-processing

Post-processing is provider-based:

- `VideoUpscalerProvider`
- `FrameInterpolationProvider`

This keeps generation jobs independent of a specific upscaler or interpolation implementation.

## Phase 1 provider

`FFmpegUpscaler` is the initial stable Windows baseline. It performs high-quality Lanczos resizing, pads only when required to preserve aspect, copies compatible audio, and encodes H.264/yuv420p for broad preview compatibility.

It is deliberately labeled **resize**, not AI upscale. The result panel and metadata preserve the distinction between H3 generation dimensions and final dimensions.

Target dimensions are aspect-aware. For example:

| Aspect | 1080p output |
|---|---:|
| 16:9 | 1920 × 1080 |
| 9:16 | 1080 × 1920 |
| 1:1 | 1080 × 1080 |
| 4:3 | 1440 × 1080 |
| 3:4 | 1080 × 1440 |
| 21:9 | 2520 × 1080 |

Choosing 1080p, 1440p, or 4K runs this stage automatically before a generation becomes complete. The original MP4 is preserved beside the final output.

## Phase 3 AI providers

Phase 3 adds two real local providers. They share the H3 Local Studio queue, release ComfyUI model memory before and after execution, sample RAM/VRAM once per second, and block a new run when the machine is already under unsafe memory pressure.

**FlashVSR · Fast 1080p** uses FlashVSR v1.1 through the pinned `ComfyUI-FlashVSR_Stable` integration. The RTX 5070 Ti profile uses SDPA rather than optional attention wheels, BF16 auto-detection, a 0.75 input factor followed by the model's 2× restoration, 384-pixel overlapping tiles, 21-frame temporal chunks, CPU model retention, and explicit DiT unload. Its four files total 6,948,393,553 bytes and live in `models\FlashVSR-v1.1`.

**SeedVR2 · Best Quality 1080p** uses ComfyUI's native SeedVR2 nodes and the official 3B INT8 ConvRot workflow family. It scales the source to an aspect-preserving 1080p content rectangle, uses the FP16 EMA VAE with tiled encode/decode, automatic temporal chunks with one-frame overlap, and a one-step Euler/simple restoration. Its two files total 3,959,584,518 bytes.

Both providers preserve the original MP4 and create an independent variant:

```text
<generation-id>_1080p_flashvsr.mp4
<generation-id>_1080p_seedvr2.mp4
```

Finalization maps the provider's video stream with the original audio stream, encodes H.264/yuv420p at 24 fps, preserves aspect with Lanczos fit/pad, and validates exact dimensions, duration, FPS, and audio through FFprobe. A failed/cancelled variant cannot overwrite or hide the completed original.

Models are pinned to immutable repository revisions with exact sizes and SHA-256 values. Installation is resumable and atomic, and requires an explicit large-download confirmation. Managed ComfyUI installs the pinned Flash custom node and `triton-windows` dependency without replacing the working Torch/CUDA stack; external ComfyUI is never modified automatically.

## Frame interpolation

The interpolation interface exists, but no implementation is presented as working. A future RIFE provider can add 48 or 60 FPS after upscaling. It must preserve audio timing and report its own progress stage before final encode.

## Thumbnails

FFmpeg extracts a single JPEG poster frame after final output processing. History cards request that small file and never load complete MP4 files into memory.
