#!/usr/bin/env python3
"""Cut a raw talking-head take the way a careful human editor does: keep the best take of every line,
drop false starts and retakes, and leave short, natural pauses (numbers measured from a real hand edit,
see ../SKILL.md).

    python smart_cut.py raw.mp4 out.mp4 --script script.txt          # cut + render
    python smart_cut.py raw.mp4 out.mp4 --script script.txt --edl-only   # write out.edl.json only (review it)
    python smart_cut.py raw.mp4 out.mp4 --apply out.edl.json         # render an EDL you (or Claude) edited

script.txt: one spoken line per line, a BLANK line where a new beat starts (new point, reveal, call to action).
Without --script every phrase is kept (silences are still tightened) - retakes then need a human/Claude pass on the EDL.

Needs ffmpeg, numpy, soundfile, and whisper.cpp (HYPERFRAMES_WHISPER_PATH or --whisper; model ggml-medium.bin).
"""
import argparse, difflib, json, os, re, subprocess, sys, tempfile
import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding='utf-8')
SR = 16000
FR = 0.01                      # analysis frame (s)

# ---- numbers measured from the reference hand edit (113 s raw -> 25.3 s, 15 cuts) ----
PAUSE_LINK = 0.18              # pause left between lines that belong together (measured 100-245 ms, median ~185)
PAUSE_BEAT = 0.42              # pause left before a new beat (measured 300-500 ms, median ~415), put BEFORE the next word
PRE_ROLL = 0.09                # silence kept before the very first word (measured 90 ms)
END_HOLD = 0.84                # silence kept after the last word (measured 840 ms, room for the end card)
TIGHT = 0.008                  # how close to the speech edge a cut goes when that side borders unwanted speech
INNER_MAX = 0.22               # pauses inside a kept line longer than this are shrunk ...
INNER_TO = 0.16                # ... to this (measured: 460 ms -> 160 ms)
LIST_INNER_MAX = 0.55          # ... but pauses between items of a list are kept up to this (measured 250 and 500 ms kept)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def thai_norm(s):
    s = s.lower()
    return re.sub(r'[^฀-๿a-z0-9]', '', s)


def sim(a, b):
    a, b = thai_norm(a), thai_norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ------------------------------------------------------------------ audio analysis
def levels(x):
    n = int(FR * SR)
    return np.array([20 * np.log10(np.sqrt(np.mean(x[i:i + n] ** 2)) + 1e-9) for i in range(0, len(x) - n, n)])


def speech_runs(act, min_gap=0.25, min_len=0.12):
    """runs of speech frames; gaps shorter than min_gap stay inside one phrase"""
    runs, i, n = [], 0, len(act)
    while i < n:
        if act[i]:
            j = i
            while j < n and act[j]:
                j += 1
            runs.append([i * FR, j * FR])
            i = j
        else:
            i += 1
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < min_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [r for r in merged if r[1] - r[0] >= min_len]


def quiet_point(lv, t, span=0.12):
    """lowest-energy frame within +-span of t (where a cut is least audible)"""
    a, b = max(0, int((t - span) / FR)), min(len(lv) - 1, int((t + span) / FR))
    return (a + int(np.argmin(lv[a:b + 1]))) * FR if b > a else t


# ------------------------------------------------------------------ transcription (whisper.cpp, token timings)
def degenerate(txt):
    t = thai_norm(re.sub(r'\[.*?\]', '', txt))
    base = re.sub(r'[ัิ-ฺ็-๎]', '', t)
    return len(set(base)) < 2 or len(base) < 0.4 * len(t)


def transcribe(wav, phrases, whisper, model, lang, prompt='', group_gap=0.8):
    """Phrases closer than group_gap are transcribed together as one chunk (a list like 'ซับ / ภาพ / เอฟเฟกต์' said with
    pauses is too short to recognise word by word), then each token goes back to the phrase it falls in.
    The script is passed as a prompt so whisper spells the words the way the script does."""
    x, _ = sf.read(wav)
    tmp = tempfile.mkdtemp(prefix='smartcut_')
    groups = []
    for k, (a, b) in enumerate(phrases):
        if groups and a - phrases[groups[-1][-1]][1] < group_gap:
            groups[-1].append(k)
        else:
            groups.append([k])
    files = []
    for g, ks in enumerate(groups):
        a, b = phrases[ks[0]][0], phrases[ks[-1]][1]
        f = os.path.join(tmp, f'g{g:03d}.wav')
        sf.write(f, x[int(max(0, a - 0.05) * SR):int((b + 0.05) * SR)], SR)
        files.append((f, a - 0.05, ks))
    cmd = [whisper, '-m', model, '-l', lang, '-ojf', '-np']
    if prompt:
        cmd += ['--prompt', prompt[:600]]
    for f, _, _ in files:
        cmd += ['-f', f]
    run(cmd)
    # a prompt sometimes derails whisper on a short chunk (output like '๋๋๋๋'); redo those chunks without it
    bad = []
    for f, _, _ in files:
        txt = ''.join(t.get('text', '') for sg in json.load(open(f + '.json', encoding='utf-8')).get('transcription', []) for t in sg.get('tokens', []))
        if degenerate(txt):
            bad.append(f)
    if bad and prompt:
        cmd = [whisper, '-m', model, '-l', lang, '-ojf', '-np']
        for f in bad:
            cmd += ['-f', f]
        run(cmd)
    out = [dict(text='', tokens=[]) for _ in phrases]
    for f, t0, ks in files:
        js = json.load(open(f + '.json', encoding='utf-8'))
        for seg in js.get('transcription', []):
            for t in seg.get('tokens', []):
                s = t.get('text', '')
                if s.startswith('[') or s.startswith('<|') or not thai_norm(s):
                    continue
                tm = t0 + t['offsets']['from'] / 1000
                k = min(ks, key=lambda q: 0 if phrases[q][0] - 0.05 <= tm <= phrases[q][1] else min(abs(tm - phrases[q][0]), abs(tm - phrases[q][1])))
                out[k]['tokens'].append((tm, s))
                out[k]['text'] += s
    for o in out:
        o['text'] = o['text'].strip()
    return out


# ------------------------------------------------------------------ choose takes against the script
def align(lines, phr, max_span=3):
    """monotone alignment script-lines -> spans of consecutive phrases, maximising total similarity.
    Phrases not used by any line are dropped (false starts, retakes, chatter)."""
    L, P = len(lines), len(phr)
    NEG = -1e9
    best = [[NEG] * (P + 1) for _ in range(L + 1)]
    back = [[None] * (P + 1) for _ in range(L + 1)]
    for p in range(P + 1):
        best[0][p] = 0.0
    for i in range(1, L + 1):
        for p in range(1, P + 1):
            # line i ends at phrase p-1, spans 1..max_span phrases
            for span in range(1, max_span + 1):
                s0 = p - span
                if s0 < 0:
                    break
                txt = ''.join(phr[q]['text'] for q in range(s0, p))
                sc = sim(txt, lines[i - 1]['text'])
                # previous line may end anywhere at or before s0 (skipped phrases are dropped)
                prev = max(range(0, s0 + 1), key=lambda q: best[i - 1][q])
                v = best[i - 1][prev] + sc + 0.0001 * p      # tiny bias: among equal takes prefer the later one
                if v > best[i][p]:
                    best[i][p], back[i][p] = v, (s0, prev, sc)
    p = max(range(P + 1), key=lambda q: best[L][q])
    picks = []
    for i in range(L, 0, -1):
        s0, prev, sc = back[i][p]
        picks.append(dict(line=i - 1, phrases=list(range(s0, p)), score=round(sc, 3)))
        p = prev
    return picks[::-1]


def trim_restart(seg_toks, line_text, start, end):
    """drop a false start inside the take ('คลิปที่ดู... คลิปที่คุณดูอยู่') by trying every token boundary as the start"""
    base = sim(''.join(t for _, t in seg_toks), line_text)
    best = (base, start)
    for k in range(1, len(seg_toks)):
        t0 = seg_toks[k][0]
        if t0 - start < 0.25 or end - t0 < 0.4:
            continue
        rest = ''.join(t for _, t in seg_toks[k:])
        dropped = ''.join(t for _, t in seg_toks[:k])
        s = sim(rest, line_text)
        # a false start repeats itself: what is dropped must look like the beginning of what is kept
        if s > best[0] + 0.08 and sim(dropped, thai_norm(rest)[:len(thai_norm(dropped)) + 2]) >= 0.5:
            best = (s, t0)
    return best[1], round(best[0] - base, 3)


def is_list(line):
    items = line.split()
    return len(items) >= 3 and np.mean([len(thai_norm(i)) for i in items]) <= 7


# ------------------------------------------------------------------ build the edit decision list
def build_edl(src, script, whisper, model, lang, fps):
    tmp = tempfile.mkdtemp(prefix='smartcut_')
    wav = os.path.join(tmp, 'a.wav')
    run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-map', '0:a:0', '-ar', str(SR), '-ac', '1', wav])
    x, _ = sf.read(wav)
    lv = levels(x)
    loud = np.percentile(lv, 95)
    act = lv > loud - 35                     # loose: voice incl. soft onsets and trailing breath -> used to find phrases
    strict = lv > loud - 25                  # strict: the voiced word itself -> every cut is measured from these edges
    phrases = [strict_edges(strict, a, b) for a, b in speech_runs(act)]
    print(f'{len(phrases)} phrases found in {len(x)/SR:.1f} s of raw audio; transcribing...')
    prompt = ' '.join(l.strip() for l in open(script, encoding='utf-8') if l.strip()) if script else ''
    tr = transcribe(wav, phrases, whisper, model, lang, prompt)
    phr = [dict(start=round(a, 3), end=round(b, 3), **t) for (a, b), t in zip(phrases, tr)]

    if script:
        raw_lines = open(script, encoding='utf-8').read().splitlines()
        lines, beat = [], True
        for l in raw_lines:
            if not l.strip():
                beat = True
                continue
            lines.append(dict(text=l.strip(), beat=beat))
            beat = False
        picks = align(lines, phr)
    else:
        lines = [dict(text=p['text'], beat=False) for p in phr]
        picks = [dict(line=k, phrases=[k], score=1.0) for k in range(len(phr))]

    keep = []
    for pk in picks:
        ln = lines[pk['line']]
        ps = [phr[q] for q in pk['phrases']]
        start, end = ps[0]['start'], ps[-1]['end']
        toks = [t for p in ps for t in p['tokens']]
        new_start, gain = trim_restart(toks, ln['text'], start, end)
        note = ''
        if new_start != start:
            new_start = quiet_point(lv, new_start - 0.03, 0.1)
            note = f'false start removed (+{gain} match)'
            start = new_start
        keep.append(dict(line=ln['text'], beat=ln['beat'], take_score=pk['score'], start=start, end=end, note=note,
                         phrases=[(p['start'], p['end']) for p in ps], heard=''.join(p['text'] for p in ps),
                         alternates=[q for q in range(len(phr)) if q not in pk['phrases'] and sim(phr[q]['text'], ln['text']) > 0.6]))

    # pauses: the gap left at each join is taken from whichever side has silence; tight on the side that borders unwanted speech
    segs = []
    n_raw = len(x) / SR
    for k, kp in enumerate(keep):
        # inner pauses of the kept line
        inner = []
        cap = LIST_INNER_MAX if is_list(kp['line']) else INNER_MAX
        for (a1, b1), (a2, b2) in zip(kp['phrases'], kp['phrases'][1:]):
            if a2 - b1 > cap:
                inner.append((b1, a2))
        pieces, cur = [], kp['start']
        for b1, a2 in inner:
            if b1 <= cur:
                continue
            keep_gap = INNER_TO if cap == INNER_MAX else cap
            pieces.append([cur, b1 + keep_gap * 0.7])      # the editor keeps the pause mostly after the word
            cur = a2 - keep_gap * 0.3
        pieces.append([cur, kp['end']])
        for pc in pieces:
            segs.append(dict(start=pc[0], end=pc[1], line=k))
    # joins between lines
    out = []
    for k, s in enumerate(segs):
        s = dict(s)
        first_of_line = k == 0 or segs[k - 1]['line'] != s['line']
        last_of_line = k == len(segs) - 1 or segs[k + 1]['line'] != s['line']
        if k == 0:
            s['start'] = max(0, s['start'] - PRE_ROLL)
        elif first_of_line:
            P = PAUSE_BEAT if keep[s['line']]['beat'] else PAUSE_LINK
            prev = out[-1]
            # silence available after the previous line / before this one in the raw take
            # usable pause = anything that is not a voiced word (the editor keeps breaths inside pauses: measured peaks
            # around -35 dB in kept pauses), so availability is measured with the strict detector
            avail_tail = max(0, next_speech_after(strict, prev['end']) - prev['end'])
            avail_lead = max(0, s['start'] - last_speech_before(strict, s['start']))
            if keep[s['line']]['beat']:
                # before a new beat: cut tight after the last word, the pause (and the in-breath) sits before the next word
                lead = min(avail_lead, P)
                tail = min(avail_tail, P - lead)
            else:
                tail = min(avail_tail, P / 2)
                lead = min(avail_lead, P - tail)
                tail = min(avail_tail, P - lead)
            prev['end'] = prev['end'] + max(TIGHT, tail)
            s['start'] = s['start'] - max(TIGHT, lead)
            s['pause_before'] = round(tail + lead, 3)
        if k == len(segs) - 1:
            s['end'] = min(n_raw, s['end'] + END_HOLD)
        out.append(s)
    # snap to the output frame grid
    for s in out:
        s['start'] = round(round(s['start'] * fps) / fps, 4)
        s['end'] = round(round(s['end'] * fps) / fps, 4)
    edl = dict(source=os.path.abspath(src), fps=fps, numbers=dict(PAUSE_LINK=PAUSE_LINK, PAUSE_BEAT=PAUSE_BEAT, PRE_ROLL=PRE_ROLL, END_HOLD=END_HOLD),
               lines=keep, segments=out, phrases=[dict(start=p['start'], end=p['end'], text=p['text']) for p in phr])
    return edl


def strict_edges(strict, a, b):
    """shrink a loose phrase to its first/last strictly voiced frame (drops soft lead-in noise and trailing breath)"""
    i, j = int(a / FR), int(b / FR)
    while i < j and not strict[i]:
        i += 1
    while j > i and not strict[j - 1]:
        j -= 1
    return (i * FR, j * FR) if j > i else (a, b)


def next_speech_after(act, t):
    i = int(t / FR) + 1
    while i < len(act) and not act[i]:
        i += 1
    return i * FR


def last_speech_before(act, t):
    i = int(t / FR) - 1
    while i > 0 and not act[i]:
        i -= 1
    return (i + 1) * FR


# ------------------------------------------------------------------ render
def render(edl, out):
    src, fps = edl['source'], edl['fps']
    segs = [s for s in edl['segments'] if s['end'] - s['start'] > 0.02]
    fc, cat = [], ''
    for k, s in enumerate(segs):
        d = s['end'] - s['start']
        fc.append(f"[0:v:0]trim={s['start']}:{s['end']},setpts=PTS-STARTPTS,fps={fps}[v{k}]")
        fc.append(f"[0:a:0]atrim={s['start']}:{s['end']},asetpts=PTS-STARTPTS,afade=t=in:d=0.006,afade=t=out:st={max(0, d-0.006):.4f}:d=0.006[a{k}]")
        cat += f'[v{k}][a{k}]'
    fc.append(f'{cat}concat=n={len(segs)}:v=1:a=1[v][a]')
    # passed inline: ffmpeg 8 dropped -filter_complex_script, and ~60 segments stay far below the command-line limit
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-g', str(int(fps)), '-keyint_min', str(int(fps)),
                    '-sc_threshold', '0', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', out], check=True)


def report(edl):
    tot = sum(s['end'] - s['start'] for s in edl['segments'])
    print(f"\n{len(edl['lines'])} lines kept, {len(edl['segments'])} segments, {len(edl['segments'])-1} cuts, output {tot:.2f} s")
    for k, l in enumerate(edl['lines']):
        flag = '' if l['take_score'] >= 0.6 else '   <-- weak match, check this line'
        alt = f"  (other takes at {', '.join(str(edl['phrases'][q]['start']) for q in l['alternates'])})" if l['alternates'] else ''
        print(f"{'|' if l['beat'] else ' '} {l['start']:7.2f}-{l['end']:7.2f}  match {l['take_score']:.2f}  {l['heard']}{alt}{('  [' + l['note'] + ']') if l['note'] else ''}{flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--script')
    ap.add_argument('--apply', help='render this EDL json instead of analysing')
    ap.add_argument('--edl-only', action='store_true')
    ap.add_argument('--fps', type=float, default=30)
    ap.add_argument('--lang', default='th')
    ap.add_argument('--whisper', default=os.environ.get('HYPERFRAMES_WHISPER_PATH', 'whisper-cli'))
    ap.add_argument('--model', default=os.path.expanduser('~/.cache/hyperframes/whisper/models/ggml-medium.bin'))
    a = ap.parse_args()
    if a.apply:
        edl = json.load(open(a.apply, encoding='utf-8'))
    else:
        edl = build_edl(a.src, a.script, a.whisper, a.model, a.lang, a.fps)
        json.dump(edl, open(os.path.splitext(a.out)[0] + '.edl.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        report(edl)
        if a.edl_only:
            print('EDL written:', os.path.splitext(a.out)[0] + '.edl.json')
            return
    render(edl, a.out)
    print('rendered', a.out)


if __name__ == '__main__':
    main()
