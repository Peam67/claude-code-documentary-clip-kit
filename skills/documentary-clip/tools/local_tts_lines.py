#!/usr/bin/env python3
"""Free narrator voice-over on this PC's NVIDIA GPU, line by line (Thai works with both engines).

    <venv>\\Scripts\\python.exe local_tts_lines.py script.txt out_dir --engine omnivoice|voxcpm2
        [--design "A middle-aged Thai man, deep resonant baritone voice, slow, serious documentary narrator"]
        [--ref voice.wav --ref-text "what the reference says"]   (skip --design and use your own 3-10 s reference)
        [--takes 3] [--limit N]

Use the environment that matches the engine (the setup script creates both):
    omnivoice : <ToolsDir>\\tts\\venv_omni\\Scripts\\python.exe
    voxcpm2   : <ToolsDir>\\tts\\venv\\Scripts\\python.exe

How it works
  * script.txt: one narration line per non-empty line.
  * Voice: with --ref the voice is cloned from your clip. Without it, line 1 is spoken in a voice designed from
    --design and saved as out_dir\\reference.wav; every other line clones that reference, so the whole narration
    keeps one consistent voice.
  * Each line is generated --takes times; every take is transcribed back with whisper.cpp and the take whose Thai text
    matches best (and whose pitch is closest to the reference) is kept -> out_dir\\line_XX.wav, narration.wav, takes.json.
  * Whisper: HYPERFRAMES_WHISPER_PATH = whisper-cli.exe, model ~/.cache/hyperframes/whisper/models/ggml-medium.bin.

Measured on an RTX 5060 Ti 8 GB, same 5 Thai lines, generation time only: OmniVoice ~2.0 GiB VRAM, RTF 0.53 (faster than real time);
VoxCPM2 ~5.5 GiB VRAM, RTF 3.6 (slower than real time). VoxCPM2 weights are loaded tensor-by-tensor straight onto the GPU because
the normal loader fails with "The paging file is too small" when little memory is free.
Licences: VoxCPM2 Apache-2.0; OmniVoice code Apache-2.0 but the PRE-TRAINED MODEL IS CC-BY-NC (non-commercial only).
"""
import argparse
import difflib
import json
import os
import re
import struct
import subprocess
import sys
import time

os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as AF

sys.stdout.reconfigure(encoding='utf-8')
WHISPER = os.environ.get('HYPERFRAMES_WHISPER_PATH', '')
WMODEL = os.path.expanduser('~/.cache/hyperframes/whisper/models/ggml-medium.bin')
DEFAULT_DESIGN = {
    'voxcpm2': 'A middle-aged Thai man, deep resonant baritone voice, slow, serious documentary narrator, cinematic',
    'omnivoice': 'male, low pitch',
}


def thai_only(s):
    return re.sub(r'[^฀-๿]', '', s)


def pitch(wav, sr):
    f0 = AF.detect_pitch_frequency(torch.tensor(np.asarray(wav, dtype=np.float32))[None], sr).numpy().ravel()
    f0 = f0[(f0 > 60) & (f0 < 400)]
    return float(np.median(f0)) if len(f0) else 0.0


def heard(path, tmp):
    """Transcribe a take with whisper.cpp. None = not available / failed (the take is then judged by pitch only)."""
    if not (WHISPER and os.path.exists(WHISPER) and os.path.exists(WMODEL)):
        return None
    for ext in ('.wav', '.txt'):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-ar', '16000', '-ac', '1', tmp + '.wav'], check=True)
    r = subprocess.run([WHISPER, '-m', WMODEL, '-l', 'th', '-f', tmp + '.wav', '-nt', '-otxt', '-of', tmp], capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp + '.txt'):
        print('   (whisper failed - usually not enough free memory; close heavy apps. Judging this take by pitch only)')
        return None
    return open(tmp + '.txt', encoding='utf-8').read().strip()


# ---------------------------------------------------------------- engines
class VoxCPM2:
    sr = 48000

    def __init__(self):
        import voxcpm.model.voxcpm2 as v2
        from voxcpm import VoxCPM
        dt = {'BF16': torch.bfloat16, 'F16': torch.float16, 'F32': torch.float32, 'I64': torch.int64, 'I32': torch.int32,
              'U8': torch.uint8, 'BOOL': torch.bool}

        def stream_load(path, device='cpu'):
            out = {}
            with open(path, 'rb') as f:
                n = struct.unpack('<Q', f.read(8))[0]
                header = json.loads(f.read(n))
                base = 8 + n
                for k, v in header.items():
                    if k == '__metadata__':
                        continue
                    a, b = v['data_offsets']
                    f.seek(base + a)
                    buf = bytearray(f.read(b - a))
                    t = torch.frombuffer(buf, dtype=dt[v['dtype']]) if b > a else torch.empty(0, dtype=dt[v['dtype']])
                    out[k] = t.reshape(v['shape']).to('cuda')
            return out

        v2.load_file = stream_load
        torch.set_default_dtype(torch.bfloat16)
        torch.set_default_device('cuda')
        self.m = VoxCPM.from_pretrained('openbmb/VoxCPM2', load_denoiser=False, optimize=False)
        torch.set_default_device('cpu')
        torch.set_default_dtype(torch.float32)
        self.sr = self.m.tts_model.sample_rate

    def design(self, text, design):
        return self.m.generate(text=f'({design}){text}', cfg_value=2.0, inference_timesteps=10)

    def clone(self, text, ref, ref_text):
        return self.m.generate(text=text, prompt_wav_path=ref, prompt_text=ref_text, reference_wav_path=ref,
                               cfg_value=2.0, inference_timesteps=10)


class OmniVoice:
    sr = 24000

    def __init__(self):
        from omnivoice import OmniVoice as OV
        self.m = OV.from_pretrained('k2-fsa/OmniVoice', device_map='cuda:0', dtype=torch.float16)

    def design(self, text, design):
        return self.m.generate(text=text, language='th', instruct=design)[0]

    def clone(self, text, ref, ref_text):
        return self.m.generate(text=text, language='th', ref_audio=ref, ref_text=ref_text)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script')
    ap.add_argument('out_dir')
    ap.add_argument('--engine', choices=['omnivoice', 'voxcpm2'], required=True)
    ap.add_argument('--design')
    ap.add_argument('--ref')
    ap.add_argument('--ref-text')
    ap.add_argument('--takes', type=int, default=3)
    ap.add_argument('--limit', type=int, default=0, help='only the first N lines (quick test)')
    a = ap.parse_args()
    if a.ref and not a.ref_text:
        sys.exit('--ref needs --ref-text (the exact words spoken in the reference clip)')

    lines = [l.strip() for l in open(a.script, encoding='utf-8') if l.strip()]
    if a.limit:
        lines = lines[:a.limit]
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    eng = VoxCPM2() if a.engine == 'voxcpm2' else OmniVoice()
    torch.cuda.synchronize()
    print(f'{a.engine} loaded in {time.time()-t0:.0f}s, VRAM now {torch.cuda.memory_allocated()/2**30:.2f} GiB')
    torch.cuda.reset_peak_memory_stats()
    sr = eng.sr

    ref, ref_text = a.ref, a.ref_text
    if not ref:
        ref = os.path.join(a.out_dir, 'reference.wav')
        design = a.design or DEFAULT_DESIGN[a.engine]
        wav = np.asarray(eng.design(lines[0], design))
        sf.write(ref, wav, sr)
        ref_text = lines[0]
        print(f'reference voice designed from: {design!r} -> {ref}')
    ref_wav, ref_sr = sf.read(ref)
    ref_pitch = pitch(ref_wav if ref_wav.ndim == 1 else ref_wav.mean(1), ref_sr)

    parts, report = [], []
    tot_gen = tot_aud = 0.0
    tmp = os.path.join(a.out_dir, '_w')
    for i, line in enumerate(lines):
        best = None
        for k in range(a.takes):
            t1 = time.time()
            wav = np.asarray(eng.clone(line, ref, ref_text))
            torch.cuda.synchronize()
            gen = time.time() - t1                      # generation only (whisper time is NOT included)
            tot_gen += gen
            tot_aud += len(wav) / sr
            p = os.path.join(a.out_dir, f'_take_{i:02d}_{k}.wav')
            sf.write(p, wav, sr)
            h = heard(p, tmp)
            acc = difflib.SequenceMatcher(None, thai_only(line), thai_only(h)).ratio() if h is not None else 0.0
            pz = pitch(wav, sr)
            score = acc - abs(pz - ref_pitch) / 200
            print(f'line {i} take {k}: {len(wav)/sr:4.2f}s audio, generated in {gen:4.1f}s (RTF {gen/(len(wav)/sr):.2f})  text {acc*100:5.1f}%  pitch {pz:4.0f} Hz  heard: {h}')
            if best is None or score > best[0]:
                best = (score, wav, acc, pz, h)
        sf.write(os.path.join(a.out_dir, f'line_{i:02d}.wav'), best[1], sr)
        parts.append(best[1])
        report.append({'line': line, 'text_match': round(best[2], 3), 'pitch_hz': round(best[3]), 'heard': best[4]})
    gap = np.zeros(int(sr * 0.25), dtype=parts[0].dtype)
    sf.write(os.path.join(a.out_dir, 'narration.wav'), np.concatenate([x for w in parts for x in (w, gap)]), sr)
    json.dump(report, open(os.path.join(a.out_dir, 'takes.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for f in os.listdir(a.out_dir):
        if f.startswith('_'):
            os.remove(os.path.join(a.out_dir, f))
    print(f'generation RTF {tot_gen/max(tot_aud,1e-9):.2f} ({tot_gen:.0f}s for {tot_aud:.0f}s of audio) | peak VRAM during generation {torch.cuda.max_memory_allocated()/2**30:.2f} GiB | done -> {os.path.join(a.out_dir, "narration.wav")}')


if __name__ == '__main__':
    main()
