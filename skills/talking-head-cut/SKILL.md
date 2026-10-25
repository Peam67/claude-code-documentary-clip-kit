---
name: talking-head-cut
description: Cut a raw talking-head recording the way the kit's author cuts by hand - keep the best take of every line, drop false starts, retakes and stumbles, and tighten the gaps to short natural pauses (numbers measured from a real hand edit). Use before any edit/motion work when the user hands over a raw take with mistakes and long silences, or says ตัดคำผิด, ตัดช่องไฟ, ตัดช่วงเงียบ, ตัดให้กระชับ, เลือกเทคที่ดี, cut my mistakes / tighten my recording.
---

# Talking-head cut (mistakes + gaps), learned from a hand edit

Goal: the same result a careful human editor gets in a timeline, from a raw take where the speaker repeats lines until
they are right. This is the step BEFORE any graphics; `documentary-clip` (and any HyperFrames build) starts from its output.

## What the hand edit actually does (measured, not guessed)

Reference pair: a 113.0 s raw phone recording -> the author's 25.31 s cut (15 cuts, 16 kept pieces). Every cut point was
found by matching the cut's audio back onto the raw take (sample-accurate), then measured against the voice level.
"Voiced" below = within 25 dB of loud speech; breaths and room tone are quieter than that.

| What | Measured | Rule it gives |
|---|---|---|
| Takes | every line was said 1-4 times; the kept take was the clean, complete one - NOT always the last (one line: 3rd of 4) | pick the take that matches the script best; tie -> the later one |
| False start inside a take ("คลิปที่ดู... คลิปที่คุณดูอยู่") | cut at the restart, the first fragment is dropped | drop a fragment that repeats the start of what follows |
| Pause between lines that belong together | 100-245 ms of silence left (median ~185 ms) | `PAUSE_LINK = 0.18 s` |
| Pause before a new beat (new point, reveal, list, call to action) | 300-500 ms left (median ~415 ms) | `PAUSE_BEAT = 0.42 s` |
| Which side of the cut keeps the pause | one side is cut tight (0-20 ms from the voice), the pause lives on the other side; before a new beat it is usually BEFORE the next word (the in-breath stays) | tight on the side that touches unwanted speech; before beats, pause on the lead side |
| Breaths | kept inside pauses (peaks around -35 dB vs speech in kept pauses) | do not gate breaths out of pauses; only the length is controlled |
| Long pause inside one line | 460 ms -> cut to ~160 ms | inner pauses > 220 ms shrink to 160 ms |
| Pauses between items of a spoken list ("ซับ ภาพ เอฟเฟกต์") | 250 ms and 500 ms left untouched | list pauses kept up to 550 ms - the rhythm of the list is intended |
| Very start | 93 ms before the first voiced frame | `PRE_ROLL = 0.09 s` |
| Very end | 840 ms of silence kept after the last word | `END_HOLD = 0.84 s` (room for the end card) |
| Small stumble ("เดี๋ยว เดี๋ยว ผม...") | left in | do not chase every repeated syllable; a natural repeat is fine |
| Overall | 22% of the raw kept; one cut every ~1.6 s of speech | sanity check for the result |

Where the hand edit still differs from the rule (be honest about these when you report):
before two of the beats the editor also shaved ~0.3 s off a drawn-out last vowel ("เหมือนเดิม", "ไม่น่าเบื่อ") to make the
line end snappier; the tool keeps the whole voiced vowel. On the test pair the tool's cut points were within a median
69 ms (about 2 frames) of the hand cut, 80% within 224 ms; the output was 26.7 s vs 25.3 s, with the same takes chosen
for all 15 lines.

## How to do it

1. **Ask for the script** (what the speaker meant to say), one line per line, with a **blank line before every new beat**:
   ```
   เอาตรงๆนะ ไม่มีใครสนใจหรอกว่า
   คุณจะจ่ายค่าจ้างตัดต่อไปเท่าไหร่

   คลิปที่คุณดูอยู่เนี่ย
   ```
   No script? Transcribe first (step 2 prints every phrase), write the script from what the speaker clearly intended,
   and show it to the user before cutting.
2. **Analyse** (nothing is rendered yet):
   ```
   python tools/smart_cut.py raw.mp4 out.mp4 --script script.txt --edl-only
   ```
   It finds phrases from the audio level, transcribes them with whisper.cpp (the script is used as a prompt), aligns the
   script to the phrases (monotone, best match per line, so earlier failed takes are skipped automatically), removes
   false starts inside a take, places the pauses with the numbers above and snaps every cut to the output frame grid.
   It prints one row per kept line: time range in the raw, match score, what whisper heard, other takes it skipped.
3. **Review the EDL like an editor** (`out.edl.json`):
   - any line marked `weak match` (< 0.6): check `heard`; English words written in Thai script (or the reverse) score low
     but are usually right; a real wrong take needs its `start`/`end` changed to the alternate listed.
   - `alternates`: if the user prefers another take, swap the line's range.
   - pauses: `segments[*].pause_before` shows what each join leaves. Make a beat longer/shorter by moving the segment
     edge, never by speeding up speech.
4. **Render** the reviewed EDL:
   ```
   python tools/smart_cut.py raw.mp4 out.mp4 --apply out.edl.json
   ```
   Output: H.264 at 30 fps, a keyframe every second (what HyperFrames wants), 6 ms audio fades at every join so cuts
   never click.
5. **Verify**: transcribe the result (whisper) and compare with the script - every line once, in order, no stray
   fragments. Report the numbers (raw length, output length, number of cuts) and say you cannot hear it: the user
   should listen to every join once.

## Traps

| Trap | What happens | Fix |
|---|---|---|
| Phone/action-cam files with extra streams (DJI: thumbnail + data tracks) | ffmpeg picks the wrong video stream | the tool maps `0:v:0` and `0:a:0` |
| Very short phrases (a list said word by word) | whisper hears nonsense or hearts/emoji | phrases closer than 0.8 s are transcribed together; chunks that come back as junk are re-run without the prompt |
| Script says "Claude", speaker says it in Thai, whisper writes "คลอด" | low match score | expected; read `heard` before replacing a take |
| ffmpeg 8 | `-filter_complex_script` no longer exists | the tool passes the filter inline |
| Cutting by fixed silence threshold only (old `tighten_silence.py`) | keeps every retake, every gap the same length | use this tool when there are retakes; `tighten_silence.py` is only for clean takes |
