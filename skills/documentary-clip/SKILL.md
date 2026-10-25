---
name: documentary-clip
description: Make a fast-cut "documentary-style" explainer clip - talking-head hook, then a deep narrator voice-over over picture-per-word b-roll, word-by-word Thai captions, big hero words, counters, strobe recap, end card and CTA - with HyperFrames, free stock footage, and an ElevenLabs (or VoiceStudio) Thai voice. Use when the user asks for a documentary-style / "AI edited" / fast-cut clip from their own talking-head footage plus a script, or says ทำคลิปสไตล์สารคดี, ทำคลิปแบบนี้, ตัดต่อให้เหมือนต้นฉบับ.
---

# Documentary-style clip (HyperFrames)

You turn the user's raw talking-head clip + a narration script into a ~45-60 s horizontal (1920x1080, 30 fps) clip whose
pictures change on almost every important word. This skill is the *recipe and the traps*; the mechanics of writing and
rendering a HyperFrames project live in the HyperFrames skills (`/hyperframes`, `/hyperframes-cli`, `/media-use`,
`/hyperframes-registry`) - read them first, they own the composition contract.

The motion numbers (frames, sizes, easings, transitions) are in `references/motion-library.md`. Read it before building.

## 0. Before you start: look at the machine, then ask (do this BEFORE downloading anything)

1. **Run the preflight** (it changes nothing):
   `powershell -ExecutionPolicy Bypass -File <this skill>/tools/preflight.ps1 -Voice api -ClipSeconds <expected length>`
   (add `-Json` if you want to parse it). It reports what is already installed, free space on the install drive and on the
   TEMP drive, RAM / pagefile headroom, the GPU and its VRAM, how many GB would still have to be downloaded, and OK / WARN / BLOCK.
   Show the user the table in plain words. Never download anything while the verdict is BLOCK.
2. **Ask which voice option** (use the AskUserQuestion tool, one question, recommend by the preflight numbers) and re-run the
   preflight with that `-Voice` so the user sees the real GB:
   - `api` - ElevenLabs through the API. 0 GB. Needs the user's own key. Free accounts: premade voices + `eleven_v3` only.
   - `voicestudio` - free app (AGPL-3.0) that makes voices on the user's PC; ~10 GB (figure from its own install guide, NOT measured here).
     Its default engine OmniVoice has a **CC-BY-NC model: non-commercial only**. Measured earlier by calling OmniVoice directly (not through the app)
     on an RTX 5060 Ti 8 GB: ~2 GB VRAM, ~2x faster than real time; its optional VoxCPM2 engine: ~5.5 GB VRAM, ~3.6x slower than real time.
     The setup script downloads the official installer, checks its SHA-256 and starts it; this path is untested by the kit's author.
   - `none` - the user brings their own audio.
   Recommend `api` unless the user wants a free local voice; recommend against `voicestudio` when the install drive is tight.
3. **Install** with `setup/SETUP_clip_maker.ps1 -Voice <choice>` (it runs the same preflight and stops on BLOCK). It only installs what is missing.
4. **Space while rendering:** a 1080p30 render writes ~0.02 GB of temporary frames per second of video (measured: 1.03 GB for
   a 50 s clip). Keep at least `max(5, 0.04 x seconds + 2)` GB free on the TEMP drive; if it is short, set `TEMP` and `TMP` to a
   roomier drive before `hyperframes render` (a render failed at 1.02 GB free while 1.03 GB were needed).
5. Keys are environment variables: `PIXABAY_API_KEY`, `ELEVENLABS_API_KEY`. **Never print a key**, never write one into a file
   inside the project. If the user keeps keys in text files, read them in code and only report "key works / does not work".
6. Keep the project path **short** (e.g. `D:/clips/topic`). A very long working directory breaks the npm shims on Windows.
7. You cannot hear audio. Say so in the delivery note and report what you *measured* (loudness, levels, whisper round-trip)
   separately from what only a human can judge (voice taste, pronunciation of loanwords).

## 1. Workflow

1. **Inspect the raw clip.** `ffprobe`, a 1 fps contact sheet, and a transcript (`whisper-cli -l th -m ggml-medium.bin`).
   Thai comes back as long chunks without word times: split with `pythainlp` and spread each chunk's time over the words
   by syllable weight (English words ~0.55 x letters + 1).
2. **Tighten.** If the raw take has mistakes or repeated lines, cut it with the `talking-head-cut` skill first (best take per
   line, false starts out, pauses measured from a hand edit). For a clean take, `tools/tighten_silence.py in.mp4 out.mp4` removes silent gaps (it also re-encodes with a keyframe every
   second, which HyperFrames needs - otherwise it warns about "sparse keyframes" and seeks freeze).
3. **Write the narration** - one short line per beat, in the user's language, in a single file. Spell numbers as words and
   write English terms the way you want them spoken. Keep each line <= ~15 words.
4. **Voice-over** (the option the user chose in step 0).
   - API: free ElevenLabs accounts get **premade voices only**, model **`eleven_v3`** (older models speak Thai with a foreign accent);
     library voices need a paid plan through the API. `tools/eleven_tts_lines.py` generates N takes per line and keeps the one whisper
     hears most accurately. Accounts used behind a VPN / created in bulk get blocked (`detected_unusual_activity`) and cannot be restored.
   - VoiceStudio: once the app is running and its MCP config (`.mcp.json` from its Integrations page, URL `http://localhost:3900/mcp/`) is
     loaded in Claude Code, call the `generate_speech` tool one line at a time (with `OMNIVOICE_MCP_OUTPUT_MODE=files` the audio is written to
     files instead of flooding the conversation). Make 2-3 takes per line and keep the one whisper hears most accurately. Not tested by the kit's
     author: if a call fails, say so plainly and offer ElevenLabs.
   After generating, compare each line's real duration with the slot the picture plan gives it; if a line runs long,
   **stretch the picture** for that stretch (hold/zoom) instead of speeding the voice up by more than ~5%.
5. **Plan shots.** For every noun/verb that matters, pick a picture that literally shows it (say "eye" -> an eye).
   Use the rhythm in the motion library: 0.1-0.3 s shots in the hook, 0.3-1 s in the body, 2-3 frame strobes at the end.
   Mark 6-10 "hero words" that get big type. Write the plan as data (a Python/JSON list), then generate the HTML from it.
6. **Source pictures.**
   - Stock: Pixabay API (`https://pixabay.com/api/videos/?key=...&q=...`). **Send a browser `User-Agent` header or you get 403.**
   - Public-domain art/photos: Wikimedia Commons (`Special:FilePath/<name>?width=2400`).
   - Movie/TV scenes for personal, non-commercial clips: `yt-dlp -f "bv*[height<=720]" --download-sections "*0-60" "ytsearch1:<scene>"`.
     Tell the user the platform may mute/remove the upload.
   - Crop letterboxes with `ffmpeg -vf cropdetect`, zoom 1.3-1.4x to hide logos/watermarks, then scale-crop to 1920x1080 @30 fps.
   - **HDR sources (BT.2020/PQ) must be tone-mapped to SDR** (`zscale ... tonemap=hable ... bt709`) or HyperFrames switches
     the whole render to HDR and the colours go wrong. Render with `--sdr` as well.
7. **Build the project** (see the HyperFrames skills). Structure that worked: root + 5 sub-compositions: `hook`, `doc`,
   `outro`, `caps` (captions, one track), `fx` (flashes/leaks/tiles above everything). Generate them from the plan with a script
   so a timing change is one edit + re-run.
8. **Music.** Pick the loud/drop sections by measuring RMS every 0.5 s. Duck with a sidechain compressor keyed by the actual voice
   tracks, set the bed level with a fixed gain (not dynamic `loudnorm`), silence it completely in any black hold.
9. **Check, then render.** `npx hyperframes check`, `snapshot` of every hero word/transition, whisper round-trip of the
   narration, loudness (-14 LUFS, peak <= -1 dBTP; apply the final gain linearly *after* the render with a limiter).
10. **Review against the reference** with contact sheets (2 fps) of both clips side by side; fix the biggest gaps only.

## 2. Traps we already hit (save yourself the time)

| Symptom | Cause / fix |
|---|---|
| Invert / pixelate transitions render as a white oval | CSS `mix-blend-mode` does not cross sub-composition layers. **Bake** the pixelated / inverted frame into 1-2 still frames and place them as clips. |
| Flash looks oval, not full-frame | A vignette layer sits above it. Put flashes at a higher `z-index` than the vignette. |
| `Render failed ... Disk capture may need ~1 GB` | System drive nearly full. Set `TEMP`/`TMP` elsewhere (or `--workers 1`). |
| Video frames freeze / seek failures | Source has sparse keyframes: re-encode `-g 30 -keyint_min 30`. |
| Whole render turns HDR | An HDR source clip slipped in. Tone-map it; render with `--sdr`. |
| `The paging file is too small` loading a 2B TTS model | Not enough free commit memory. Load the weights tensor-by-tensor straight onto the GPU instead of memory-mapping the file. |
| Audio overlap warnings (`duplicate_audio_track`) | Give every sound-effect clip its own `data-track-index`. |
| Hero word hard to read on a bright picture | Heavy multi-layer text-shadow + a soft dark radial behind the word; never plain white on white. |
| Captions unreadable on a phone | 44-48 px Thai serif, weight 600, heavy shadow, <= 3 words / 20 characters per group, clear the group before a black hold. |
| Pixabay returns 403 | Missing `User-Agent` header. |
| ElevenLabs `paid_plan_required` / `voice_not_found` | Library voice on a free key: use a premade voice. |
| Narrator line a different loudness than the presenter | Measure both (LUFS) and trim to within ~0.5 LU; the hand-over must have < 0.1 s of dead air. |

## 3. Delivery note (always include)

What was built; the files; the measured numbers (duration, LUFS, peak, music-under-voice dB, black-hold level); what was *not*
verified (anything that needs ears); the weakest shot; and the licence caveat for movie clips / songs (personal use; platforms
may mute or remove).
