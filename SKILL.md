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

## Agent Fast Path (mandatory)

You are an **executor**, not an architect. Do not deep-plan, multi-option design, or
“fully understand the skill” before the first successful image.

### Hard bans

1. Do **not** read `README.md`, `README_EN.md`, `README/*` samples, or skill demo images.
2. Do **not** scan plugins, alternate skill copies, or re-resolve paths for many turns.
3. Do **not** run `setup.py --check` / `--check-codex` / `--check-ccswitch` unless
   `generate`/`edit` already failed with missing config.
4. Do **not** write long plans, todo lists, or architecture notes before shot 1 succeeds.
5. Do **not** switch `--model`, downsize, or change aspect unless the user explicitly agrees.
6. Do **not** run parallel `generate` jobs. One image per call, serial only.
7. Host `timeout_ms` / `block_until_ms` must be **integers** (e.g. `900000`, never `900000.0`).
8. On failure: report `FAILURE_SUMMARY` / stderr tail only; no silent retries. At most one
   retry after the user agrees to a concrete single change.
9. Do **not** install `python-docx` / Word COM / Office interop ad hoc, and do **not**
   wait on host “Loading document dependencies”. Prefer an **installed office skill**
   (see below); if none, use this skill’s `scripts/extract_docx_text.py` only.

### Fixed path (pick one absolute path; do not probe)

```powershell
# Codex install (common)
$skill = "$HOME/.codex/skills/relay-imagegen/scripts/relay_imagegen.py"
# Agents skills install (if that is where this skill lives)
# $skill = "$HOME/.agents/skills/relay-imagegen/scripts/relay_imagegen.py"
```

Work only in the user project cwd. Use `prompts/` and `generated/` there.

### Office / script inputs (priority list + fallback)

This skill **does not own** Office parsing. Resolve script text + optional media first,
then generate. Prefer **already-installed** external skills; only then use the local
stdlib fallback.

#### Input already plain / structured — use as-is (no Office skill)

| Input | Action |
|-------|--------|
| User paste / `.txt` / `.md` | Read directly → shotlist |
| `prompts/_script.txt` already present | Read it; do not re-open the source `.docx` |
| `shotlist.csv` / `shotlist.json` / `shotlist.md` | Use as shotlist (no re-extract) |

#### External office skills — try in this order when source is binary

Only use a skill that is **already present** under the agent’s skill roots
(e.g. `~/.codex/skills/`, `~/.agents/skills/`, project `.agents/skills/`).
Do **not** clone GitHub mid-task unless the user asks.

| Priority | Skill / package (if installed) | Typical use | Upstream (install separately) |
|----------|--------------------------------|-------------|-------------------------------|
| 1 | `docx-to-md` / `doc-to-md-skills` | DOCX → markdown + extracted images (best for storyboard refs) | https://github.com/oCOZYo/doc-to-md-skills |
| 2 | Anthropic / Claude `docx` | Read/edit Word; **read** often via `pandoc -t markdown file.docx` | https://github.com/anthropics/skills (`skills/docx`) |
| 3 | Anthropic / Claude `pdf` | PDF extract/merge/forms | https://github.com/anthropics/skills (`skills/pdf`) or Composio mirror |
| 4 | `claude-office-skills` bundle | DOCX/PPTX/XLSX/PDF workflows | https://github.com/tfriedel/claude-office-skills |
| 5 | `office-mcp` / `claude-office-skills/skills` | MCP tools: `extract_text_from_docx`, PDF tools | https://github.com/claude-office-skills/skills |
| 6 | Host CLI if already on PATH | DOCX: `pandoc -t markdown file.docx`; PDF: `pdftotext file.pdf -` | pandoc / poppler |

Rules when using an external skill:

1. Follow **that** skill’s Fast Path; do not invent `pip install python-docx`.
2. Write a stable handoff into the project: `prompts/_script.txt` and, if images
   exist, `prompts/_script_media/` (or keep that skill’s media dir and reference it).
3. After handoff, **never re-parse** the original `.docx`/`.pdf` for the same run.
4. If the external skill only returns text and drops table images, fall through to
   the local fallback below (storyboard scripts often embed refs in tables).

#### Local fallback (this skill — no third-party deps)

Use when no external office skill is installed, or when table-embedded images were lost:

```powershell
$extract = "$HOME/.codex/skills/relay-imagegen/scripts/extract_docx_text.py"
# or: $HOME/.agents/skills/relay-imagegen/scripts/extract_docx_text.py
python $extract "C:/path/to/script.docx" --out prompts/_script.txt --media-dir prompts/_script_media
```

- Tables → rows with ` | `; embedded images → `[IMAGE:imageN.png]` + files in `--media-dir`.
- Optional: `python $extract --test` (self-check).
- PDF/PPTX: this fallback is **DOCX-only**. For PDF/PPTX without an external skill,
  ask the user for plain text/CSV export, or use PATH tools (`pdftotext` / pandoc) if
  already installed — do not start “Loading document dependencies” loops.

Then read only `prompts/_script.txt`. Use `_script_media/*` with `preview` / `edit` when
a shot has a matching `[IMAGE:…]` ref.

### Ordered steps (no exploration between steps)

1. **Shot list once** — from paste/CSV/JSON/MD, or Office input via **priority list →
   fallback** → `prompts/_script.txt`, then: `shot id | one-line scene | landscape|portrait`.
   Do not invent extra “cinematic” shots beyond the script.
2. **One style file** — `prompts/_style.txt` (short style + negatives). Reuse by prepending.
3. **Write all prompts** — `prompts/shot-01.txt` … `shot-NN.txt` (style + scene). Finish writing
   before any relay call.
4. **Prove the pipe once**

```powershell
python $skill generate --prompt-file prompts/shot-01.txt --name shot-01 --size 3840x2160 --force
```

   - 4K landscape `3840x2160`; 4K portrait `2160x3840`; 2K landscape `2560x1440`; 2K portrait `1440x2560`.
   - Never pass `--size 4K` / `2K` / `16:9` as CLI values.
   - Host wait ≥ `900000` ms for 4K; optional `--timeout 900` if the user needs a longer cap.
   - Success → record `OUTPUT` / size / `META`. Failure → stop and report `FAILURE_SUMMARY`.
5. **Serial remainder** — same command for shot-02…NN (only `--prompt-file` and `--name` change).
   If a PowerShell batch script breaks on quoting, fall back to one `python` call per shot.
6. **Short report** — count, output dir, size match, failed shot ids. No process essay.

### Time budget

- Steps 1–3 should start step 4 quickly. If you are still inspecting skill files / setup after
  several tool rounds with zero `generate`, you are violating this path.
- Long silent waits during `generate`/`edit` (minutes) are normal for 4K relays — do not abandon
  the job to re-read this skill or re-check config.
- Do not auto-downgrade 4K→2K “to be safe” unless the user asks or consents after a failure.

### Multi-shot / storyboard

This skill is one image per CLI call. Multi-shot means: write N prompt files → serial `generate`.
No batch subcommand required. Resume by skipping shots that already have a successful output +
matching `.meta.json` when the user wants continue-from-existing.

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

### Failure & retry policy (hard)

On any non-zero exit from `relay_imagegen.py`:

1. Report only the script `FAILURE_SUMMARY` / stderr tail to the user.
2. **Do not** switch `--model` or invent alternate models.
3. **Do not** downsize (e.g. 4K → `1536x1024`) or change aspect to “make it work”.
4. **At most one** retry, and **only** if the user explicitly agrees to a concrete change.
5. Do not spawn temp monitor scripts or multi-model matrices.

Empty `b64_json` means stop. The error looks like:

```text
Error: empty b64_json from edit (model=… size=…).
```

That is terminal unless the user consents to a new plan.

### Size vs reference vs model id (hard)

When the user provides reference / prompt images:

1. **4K / 2K size follows the reference orientation** (portrait ref → `2160x3840` /
   `1440x2560`; landscape ref → `3840x2160` / `2560x1440`). The CLI auto-aligns
   known 2K/4K tiers. Agents must pass **canonical WIDTHxHEIGHT only**, e.g.
   `--size 2160x3840` — never `--size 4K` or `--size 2K` (those are user words,
   not CLI values; the script will expand aliases, but prefer exact sizes).
2. If config `model` contains `16x9` / `9x16` / `1x1`, the CLI aligns `--size` to that
   aspect when there is **no** conflicting reference. If the model token conflicts
   with the reference orientation, the CLI **stops** with a clear error. Use
   `--allow-aspect-mismatch` only after the user agrees (do not invent another model).

If a **context window** error happens before tools run (host already injected
huge attachments), recover with a clean thread and the same flow: resolve path →
`preview` → short Read of PREVIEW → `edit` with ORIGINAL. Do not blame the user
for attaching files.

## Fast Path

Execution order and bans: see **Agent Fast Path** at the top. This section is defaults and CLI shape only.

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
- If the user asks for 4K, 2K, horizontal/landscape, vertical/portrait, square, 16:9, 9:16, 1:1, wallpaper, avatar, or any explicit framing/aspect ratio, pass `--size` as a **canonical pixel size**:
  - 2K landscape `2560x1440`; 2K portrait `1440x2560`
  - 4K landscape `3840x2160`; 4K portrait `2160x3840`
  - square `2048x2048`
  - **Never** `--size 4K` / `--size 2K` / `--size 16:9` as the CLI value (user may say “4K”; you translate to WIDTHxHEIGHT).
- **With reference images**, map 4K/2K to the **reference orientation** (portrait photo + 4K → `--size 2160x3840`, not landscape `3840x2160`). The CLI also re-aligns known tiers and expands `4k`/`2k` aliases safely.
- Do not pass `--quality` or `--timeout` unless the user asks; defaults are already useful.
- Use `prompts/<short-name>.txt` for saved prompts in the current workspace.
- Use `generated/` as the default output location.
- On Windows, avoid PowerShell ternary syntax; assign `$skill` with a plain path.
- Common sizes (only these pixel forms are valid `--size` values): 2K landscape `2560x1440`; 4K landscape `3840x2160`; 2K portrait `1440x2560`; 4K portrait `2160x3840`; square `2048x2048`.
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

If the relay rejects a model, size, or endpoint, report the exact non-secret error summary (`FAILURE_SUMMARY`) and stop. Do **not** switch model or downsize unless the user explicitly agrees. Empty `b64_json` is a hard stop, not a cue to try `1536x1024`.

If a **context window** error happens at the chat layer (script never ran): start a clean thread, keep UI attachments if the user attached them, resolve paths, run `preview`, Read only `PREVIEW` paths, then `edit` with `ORIGINAL` paths—no full-res re-open, no README, no long vision writeup.
