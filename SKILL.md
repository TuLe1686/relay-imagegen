---
name: relay-imagegen
description: >-
  Generate or edit images through a local OpenAI-compatible relay or proxy
  endpoint, with saved prompt files and non-secret run metadata. Use when the
  user wants relay/proxy image generation, reusable or saved prompts, reuse of
  current Codex or ccswitch relay config, api_key.json/base_url config, or a
  repeatable local image workflow without persistent OPENAI_API_KEY environment
  variables. UI-attached reference images are supported: resolve paths, run
  preview to compress, optionally view the small PREVIEW, then edit with ORIGINAL.
---

# Relay Imagegen

## Product stance (designers)

This skill amplifies people who already have taste and craft. The **chat model is
the director** (interpret intent, optionally polish the image prompt). The skill
is the **camera rig** (relay config, fixed `--size`, saved prompts, run records).

Do not try to force identical images across different chat models. Different
directors write different final prompts; that is expected. To compare runs, use
`prompt_sha256` / `prompt_snapshot` in `*.meta.json` and the sibling `*.prompt.txt`.

## Reference images (UI attach is normal)

Users may provide references by **chat UI attachment**, workspace path, or both.
That is the expected UX on Codex desktop and Cursor. Do **not** ask the user to
avoid attachments or to paste paths only.

### Recommended flow when the agent needs to understand the image

1. **Resolve** a filesystem path for each reference (attachment metadata or typed path).
2. **Compress for vision** (no relay call):

```powershell
python $skill preview --image C:/path/to/reference.jpg --name ref
```

   - Default max edge: `768` (override with `--max-input-edge`).
   - Prints `ORIGINAL=...` and `PREVIEW=...` under `generated/relay_preview/`.
3. **May Read only `PREVIEW` paths** for short visual notes (subject, pose, colors,
   composition). Do **not** Read the original high-res file or UI attachment again.
4. Write a short prompt to `prompts/*.txt` from those notes + user intent.
5. **Edit/upload with ORIGINAL path** (edit still prepares upload at max edge `2048`):

```powershell
python $skill edit --image C:/path/to/reference.jpg --prompt-file prompts/edit.txt --name edit --force
```

### Hard rules

1. Do **not** open original / attachment full-resolution image bytes for analysis.
2. Do **not** open `README.md`, `README/*.png`, or skill sample images.
3. Vision notes stay short; no multi-paragraph art critique.
4. After success, report output path, size check, and `.meta.json` only.
   Do not re-read the final high-res output into chat (optional: `preview` it first
   if a quick look is needed).
5. `preview` = agent vision budget. `edit --prepare-image` = relay upload budget.
   They are separate.

If a **context window** error happens before tools run (host already injected
huge attachments), recover with a clean thread and the same flow: resolve path →
`preview` → short Read of PREVIEW → `edit` with ORIGINAL. Do not blame the user
for attaching files.

## Fast Path

Use `scripts/relay_imagegen.py` directly. The defaults are tuned for low-thinking relay image runs:

- Relay/proxy config lookup without persistent system env vars.
- Saved prompts via `prompts/*.txt` and sidecar `prompt_snapshot`.
- Non-secret run metadata next to every successful output.
- Default size: `2560x1440`.
- High quality.
- Config lookup: `--config` first, then this skill's private `.secrets/config.json` if valid, then current Codex config/auth, then ccswitch, then other private config files.
- Auto output path: `generated/<name>-YYYYMMDD-HHMMSS-2k.png`.
- Edit-mode input downscaling is on by default (`--prepare-image`; disable with `--no-prepare-image`).
- Optional agent-vision downscale: `preview` (default max edge `768`) writes `PREVIEW=` under `generated/relay_preview/`.

Agent rules:

- Do not run setup checks unless config lookup fails.
- Do not pass `--output-dir` unless the user asks for a custom directory.
- Default size is `2560x1440` landscape. Omit `--size` only when the user does not request a different resolution or aspect ratio.
- If the user asks for 4K, 2K, horizontal/landscape, vertical/portrait, square, 16:9, 9:16, 1:1, wallpaper, avatar, or any explicit framing/aspect ratio, pass `--size` explicitly.
- Do not pass `--quality` or `--timeout` unless the user asks; defaults are already useful.
- Use `prompts/<short-name>.txt` for saved prompts in the current workspace.
- Use `generated/` as the default output location.
- On Windows, avoid PowerShell ternary syntax; assign `$skill` with a plain path.
- Common sizes: 2K landscape `2560x1440`; 4K landscape `3840x2160`; 2K portrait `1440x2560`; 4K portrait `2160x3840`; square `2048x2048`.
- **Host tool timeouts must be integers**: Codex/Cursor `timeout_ms` / `block_until_ms` reject floats
  such as `900000.0`. Use `900000` (no decimal). For `generate`/`edit`, prefer at least
  `900000` ms (15 minutes) wall time so 4K relay jobs are not killed early.
- Prefer one long-running shell call to `relay_imagegen.py`; do not invent extra float timeouts.

Windows path setup:

```powershell
$skill = "$HOME/.codex/skills/relay-imagegen/scripts/relay_imagegen.py"
```

Minimal generation:

```powershell
python $skill generate --prompt-file prompts/prompt.txt --name output --force
```

Require current Codex config/auth instead of falling back:

```powershell
python $skill generate --from-codex --prompt-file prompts/prompt.txt --name output --force
```

Require the current ccswitch Codex provider instead of falling back:

```powershell
python $skill generate --from-ccswitch --prompt-file prompts/prompt.txt --name output --force
```

Minimal edit with references (path may come from UI attachment metadata):

```powershell
python $skill edit --image C:/path/to/reference.jpg --prompt-file prompts/prompt.txt --name edit --force
```

When the agent needs to look at the reference first:

```powershell
python $skill preview --image C:/path/to/reference.jpg --name ref
# Read only the printed PREVIEW= path (short notes), then:
python $skill edit --image C:/path/to/reference.jpg --prompt-file prompts/prompt.txt --name edit --force
```

Prefer `--prompt-file` over `--prompt` for saved/reusable prompts, long prompts, Chinese text, or prompts that should not appear in shell history. Successful runs copy the prompt text into the sidecar metadata as `prompt_snapshot`.

## Config

Use `scripts/relay_imagegen.py` for relay image generation or editing. It reads a private JSON config only at runtime, injects `OPENAI_API_KEY` and `OPENAI_BASE_URL` only into the child process that calls the bundled imagegen CLI, then verifies output dimensions when possible.

Default config lookup:

1. `--config <path>` if provided.
2. This skill's private `.secrets/config.json` if it exists and reads successfully. If it is missing or invalid, skip it silently.
3. Current Codex config/auth from `~/.codex/config.toml` and `~/.codex/auth.json`, unless `--no-codex` is used.
4. Current ccswitch `codex` provider from `~/.cc-switch/cc-switch.db`, unless `--no-ccswitch` is used.
5. `RELAY_IMAGEGEN_CONFIG` if set.
6. `photo/api_key.json` under the current working directory.
7. `.secrets/image_api.json` under the current working directory.
8. `.secrets/relay_imagegen.json` under the current working directory.
9. `%APPDATA%/relay-imagegen/config.json` on Windows.
10. `~/.config/relay-imagegen/config.json`.
11. `~/.relay-imagegen.json`.

Expected JSON fields:

```json
{
  "api_key": "...",
  "base_url": "https://relay.example/v1",
  "model": "gpt-image-2"
}
```

Accepted aliases:

- API key: `api_key`, `apiKey`, `key`, `token`, `openai_api_key`, `OPENAI_API_KEY`
- Base URL: `base_url`, `baseUrl`, `baseURL`, `api_base`, `endpoint`, `openai_base_url`, `OPENAI_BASE_URL`

Never print the API key or pass it as a command-line argument. Do not write it to user or system environment variables. Avoid committing the config file.

For the lowest-friction cross-project setup, create the skill-local private config:

```text
<skill>/relay-imagegen/.secrets/config.json
```

Use the setup helper when available:

```powershell
$skillDir = "$HOME/.codex/skills/relay-imagegen"
python (Join-Path $skillDir "scripts/setup.py") config --scope skill
python (Join-Path $skillDir "scripts/setup.py") --check
python (Join-Path $skillDir "scripts/setup.py") --check-codex
python (Join-Path $skillDir "scripts/setup.py") --check-ccswitch
```

For project-specific or shared setups, use one of these files instead:

```text
<project>/.secrets/image_api.json
%APPDATA%/relay-imagegen/config.json
~/.config/relay-imagegen/config.json
```

Add `.secrets/` to `.gitignore` when using project-local or skill-local config. Do not package or share a real config file with the skill.

## Common Commands

Generation with default relay settings:

```powershell
python $skill generate `
  --prompt-file prompts/prompt.txt `
  --name output-2k `
  --force
```

If `--out` is omitted, the script writes a timestamped file under `--output-dir`, `RELAY_IMAGEGEN_OUTPUT_DIR`, or finally `generated`. For example: `generated/output-2k-20260526-203000-2k.png`.

Use `prompts/` for reusable prompt files in a project. Do not create `photo/prompt.txt` just because the config example uses `photo/api_key.json`; if the current workspace is already named `photo`, that would produce awkward paths such as `photo/photo/prompt.txt`.

Edit with reference images (path from UI attachment or user-provided path):

```powershell
python $skill edit `
  --image C:/path/to/composition.png `
  --image C:/path/to/character.jpg `
  --prompt-file prompts/prompt.txt `
  --name final-2k `
  --force
```

Override prepare edge or disable preparation:

```powershell
python $skill edit `
  --image C:/path/to/reference.jpg `
  --prompt-file prompts/prompt.txt `
  --max-input-edge 1536 `
  --timeout 900

python $skill edit `
  --image C:/path/to/reference.jpg `
  --prompt-file prompts/prompt.txt `
  --no-prepare-image `
  --force
```

## Options

- `--config <path>`: Override config discovery for this run.
- `--from-codex`: Require current Codex config/auth from `~/.codex/config.toml` and `~/.codex/auth.json`; fail instead of falling back.
- `--no-codex`: Skip default Codex config/auth lookup.
- `--codex-config <path>`: Override the Codex `config.toml` path.
- `--codex-auth <path>`: Override the Codex `auth.json` path.
- `--from-ccswitch`: Require the current `codex` provider from `~/.cc-switch/cc-switch.db`; fail instead of falling back.
- `--no-ccswitch`: Skip default ccswitch lookup and use file config discovery.
- `--ccswitch-db <path>`: Override the ccswitch SQLite database path.
- `--timeout <seconds>`: Cap how long the relay call can run. Default is `600`.
- `--output-dir <path>`: Directory for auto-named outputs when `--out` is omitted. Default is `generated`, or `RELAY_IMAGEGEN_OUTPUT_DIR` if set.
- `--prepare-image`: Downscale edit input images before upload. Enabled by default for `edit`. Default edge is `2048`; prepared copies are temporary and deleted after the run.
- `--no-prepare-image`: Disable default edit-mode preparation.
- `--max-input-edge <pixels>`: Downscale edit inputs to fit this max edge. Also enables image preparation.
- `--keep-prepared`: Keep prepared upload copies under `generated/relay_prepared/` for debugging.
- `--name <slug>`: Use this base name when `--out` is omitted.
- `--dry-run`: Print the non-secret command shape without calling the relay.
- `--use-system-proxy`: Keep `HTTP(S)_PROXY` from the environment. **Default is to ignore proxies** so CN-reachable relays go direct (httpx otherwise often inherits system proxy).

## Validation

After generation, report:

- Output path.
- Actual width and height.
- Whether the size matched the requested `--size`.
- Whether the call used `generate` or `edit`.
- Sidecar metadata path (`*.meta.json`).
- Prompt compare helpers when present: `PROMPT_SHA256`, `PROMPT_CHARS`, sibling `*.prompt.txt`.

The wrapper filters the noisy `OPENAI_API_KEY is set.` line from child process output. For successful calls it writes a sibling sidecar file, for example `final-2k.meta.json`, with prompt fields near the top (`prompt_snapshot`, `prompt_sha256`, `prompt_chars`, `prompt_preview`) plus mode, model, size, quality, input image paths, prepared image dimensions, output dimensions, elapsed seconds, config source/path, Codex or ccswitch provider name when used, and base URL. It also writes `final-2k.prompt.txt` with the exact prompt text for side-by-side diffs across chat models. It must never include the API key.

If the relay rejects a model, size, or endpoint, report the exact non-secret error summary and suggest the smallest next adjustment, such as testing `generate` before `edit`, checking `base_url`, or switching model only if the user asks.

If a **context window** error happens at the chat layer (script never ran): start a clean thread, keep UI attachments if the user attached them, resolve paths, run `preview`, Read only `PREVIEW` paths, then `edit` with `ORIGINAL` paths—no full-res re-open, no README, no long vision writeup.
