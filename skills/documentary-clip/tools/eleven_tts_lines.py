#!/usr/bin/env python3
"""Narrator voice-over line by line with ElevenLabs, then pick the best take by listening with whisper.

    python eleven_tts_lines.py script.txt out_dir --voice <voice_id> [--takes 3] [--key-file keys.txt]

* script.txt  one narration line per non-empty line (Thai works with model eleven_v3)
* The API key is read from --key-file (first sk_... found) or from the ELEVENLABS_API_KEY environment variable.
  It is never printed.
* Each line is generated --takes times; every take is transcribed back with whisper.cpp and the take whose
  Thai text matches the script best is kept as out_dir/line_00.wav, line_01.wav ... (48 kHz mono) + .mp3.
* Whisper: set HYPERFRAMES_WHISPER_PATH to whisper-cli.exe (the setup script does this) and have the model
  ggml-medium.bin in ~/.cache/hyperframes/whisper/models (HyperFrames downloads it on first transcribe),
  or pass --whisper-model.

Free ElevenLabs accounts can use PREMADE voices only (library voices need a paid plan) and must use
--model eleven_v3 for Thai. The older multilingual model speaks Thai with a strong foreign accent.
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')


def thai_only(s):
    return re.sub(r'[^฀-๿]', '', s)


def get_key(key_file):
    if key_file:
        txt = open(key_file, encoding='utf-8', errors='ignore').read()
        m = re.search(r'sk_[A-Za-z0-9]{20,}', txt)
        if m:
            return m.group(0)
        sys.exit(f'no sk_... key found in {key_file}')
    k = os.environ.get('ELEVENLABS_API_KEY')
    if not k:
        sys.exit('set ELEVENLABS_API_KEY or pass --key-file')
    return k.strip()


def tts(key, voice, model, text, mp3_path, lang):
    body = {'text': text, 'model_id': model}
    if lang:
        body['language_code'] = lang
    req = urllib.request.Request(
        f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128',
        data=json.dumps(body).encode(), headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    try:
        open(mp3_path, 'wb').write(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        sys.exit(f'ElevenLabs HTTP {e.code}: {e.read()[:300].decode("utf-8", "ignore")}')


def heard(mp3, tmp, whisper, wmodel):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp3, '-ar', '16000', '-ac', '1', tmp + '.wav'], check=True)
    subprocess.run([whisper, '-m', wmodel, '-l', 'th', '-f', tmp + '.wav', '-nt', '-otxt', '-of', tmp], capture_output=True)
    try:
        return open(tmp + '.txt', encoding='utf-8').read().strip()
    except OSError:
        return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script')
    ap.add_argument('out_dir')
    ap.add_argument('--voice', required=True, help='ElevenLabs voice id (a premade voice on a free account)')
    ap.add_argument('--model', default='eleven_v3')
    ap.add_argument('--lang', default='th', help='language_code, "" to omit')
    ap.add_argument('--takes', type=int, default=3)
    ap.add_argument('--key-file')
    ap.add_argument('--whisper', default=os.environ.get('HYPERFRAMES_WHISPER_PATH', ''))
    ap.add_argument('--whisper-model', default=os.path.expanduser('~/.cache/hyperframes/whisper/models/ggml-medium.bin'))
    a = ap.parse_args()

    key = get_key(a.key_file)
    use_whisper = bool(a.whisper) and os.path.exists(a.whisper) and os.path.exists(a.whisper_model)
    if not use_whisper and a.takes > 1:
        print('whisper not found - generating 1 take per line, no automatic check')
        a.takes = 1
    lines = [l.strip() for l in open(a.script, encoding='utf-8') if l.strip()]
    os.makedirs(a.out_dir, exist_ok=True)
    tmp = os.path.join(a.out_dir, '_w')
    for i, line in enumerate(lines):
        best = None
        for k in range(a.takes):
            mp3 = os.path.join(a.out_dir, f'_take_{i:02d}_{k}.mp3')
            tts(key, a.voice, a.model, line, mp3, a.lang or None)
            if use_whisper:
                h = heard(mp3, tmp, a.whisper, a.whisper_model)
                score = difflib.SequenceMatcher(None, thai_only(line), thai_only(h)).ratio()
            else:
                h, score = '', 0.0
            print(f'line {i} take {k}: match {score*100:5.1f}%  heard: {h}')
            if best is None or score > best[0]:
                best = (score, mp3)
        final = os.path.join(a.out_dir, f'line_{i:02d}.mp3')
        os.replace(best[1], final)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', final, '-ar', '48000', '-ac', '1',
                        os.path.join(a.out_dir, f'line_{i:02d}.wav')], check=True)
    for f in os.listdir(a.out_dir):
        if f.startswith('_'):
            os.remove(os.path.join(a.out_dir, f))
    print('done ->', a.out_dir)


if __name__ == '__main__':
    main()
