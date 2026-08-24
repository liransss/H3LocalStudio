# Windows development

## One-time setup

From a PowerShell window in the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script creates `backend\.venv`, installs pinned-range Python dependencies, and installs Node dependencies locally. It does not modify Python, CUDA, the NVIDIA driver, Windows security settings, or machine-wide `PATH`.

If Python 3.12 is not registered with the launcher, create the venv explicitly with an available Python 3.11+ executable and then rerun the pip command from `scripts\setup.ps1`.

## Run the application

```powershell
npm.cmd run dev
```

Services:

- UI: `http://127.0.0.1:1420`
- API: `http://127.0.0.1:7331`
- API docs: `http://127.0.0.1:7331/api/docs`
- ComfyUI default: `http://127.0.0.1:8188`

The development command uses Mock Mode. Stop it with `Ctrl+C`.

## Environment overrides

Copy `.env.example` to `backend\.env`, then edit only local values:

```powershell
Copy-Item -LiteralPath .env.example -Destination backend\.env
```

Supported settings include:

```text
H3_MOCK_MODE=true
H3_MOCK_STEP_DELAY=0.45
H3_MOCK_FAILURE=false
H3_DATA_ROOT=F:\AI\H3LocalStudio
H3_COMFYUI_HOST=127.0.0.1
H3_COMFYUI_PORT=8188
H3_COMFYUI_PATH=F:\AI\H3LocalStudio\runtime\ComfyUI
H3_COMFYUI_MODE=managed
H3_COMFYUI_PROFILE=balanced
H3_COMFYUI_AUTO_START=false
H3_FFMPEG_PATH=C:\path\to\ffmpeg.exe
```

Only loopback values are accepted for API and ComfyUI hosts.

## Quality checks

```powershell
backend\.venv\Scripts\python.exe -m pytest
npm.cmd run build
```

`scripts\check.ps1` runs both. ComfyUI responses and GPU inference are mocked, so ordinary tests stay fast, deterministic, and never download models.

When changing the UI, also run the development server and check:

- meaningful content renders rather than a blank page
- there is no Vite error overlay or console exception
- Create accepts a prompt
- progress reaches a terminal state
- View Result loads the MP4
- History retains the generation after refresh

## Native Tauri shell

Check prerequisites:

```powershell
npm.cmd exec tauri info
```

Then run:

```powershell
npm.cmd run desktop:dev
```

The Phase 1 Tauri capability includes only `core:default`; filesystem and command execution are handled behind validated backend endpoints. Do not broaden permissions merely to bypass API design.

## Adding a migration

Add a sequential SQL file beneath `backend\app\migrations`, for example `002_saved_prompt_tags.sql`. Migrations run in filename order and are recorded in `schema_migrations`. Never edit a migration that may already exist in a user database.

## Adding a provider

1. Implement the appropriate abstract interface in `backend\app\providers\base.py`.
2. Keep external process arguments in arrays and do not use shell interpolation.
3. Report friendly stages through the progress callback.
4. Preserve originals and unique output filenames.
5. Add non-GPU unit tests with the external process/client mocked.
6. Document exact runtime and model dependencies.

## Logs

Backend logs are written to `<data-root>\logs\backend.log`; managed ComfyUI writes to `<data-root>\logs\comfyui.log`. Full job error details are persisted for technical expansion, while the primary UI message remains human-friendly. Prompt text and media contents should not be logged.
