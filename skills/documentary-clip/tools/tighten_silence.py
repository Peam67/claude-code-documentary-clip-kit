#!/usr/bin/env python3
"""Cut the silent gaps out of a talking-head clip (keeps picture and sound in sync).

    python tighten_silence.py input.mp4 output.mp4 [--noise -35] [--min-gap 0.15] [--pad 0.04] [--fps 30]

Needs ffmpeg + ffprobe on PATH. Re-encodes to H.264 with a keyframe every second (-g = fps),
which HyperFrames needs for reliable seeking. Prints the kept segments and the new duration.
"""
import argparse
import re
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--noise', type=float, default=-35, help='dB below which audio counts as silence')
    ap.add_argument('--min-gap', type=float, default=0.15, help='shortest silence (s) that gets cut')
    ap.add_argument('--pad', type=float, default=0.04, help='breathing room (s) kept on each side of a cut')
    ap.add_argument('--fps', type=int, default=30)
    a = ap.parse_args()

    log = subprocess.run(['ffmpeg', '-hide_banner', '-i', a.src, '-af', f'silencedetect=noise={a.noise}dB:d={a.min_gap}',
                          '-f', 'null', '-'], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', log)]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', log)]
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.src],
                               capture_output=True, text=True).stdout)

    keep, cur = [], 0.0
    for s, e in zip(starts, ends):
        if s < 0.05:                       # leading silence: just skip it
            cur = max(0.0, e - a.pad)
            continue
        keep.append((cur, s + a.pad))
        cur = e - a.pad
    if len(ends) < len(starts):            # file ends inside a silence: stop at its start
        pass
    elif dur - cur > 0.1:
        keep.append((cur, dur))
    keep = [(round(x, 3), round(y, 3)) for x, y in keep if y - x > 0.05]
    if not keep:
        sys.exit('nothing to keep - try a lower --noise value')

    parts = []
    for i, (x, y) in enumerate(keep):
        parts.append(f'[0:v]trim={x}:{y},setpts=PTS-STARTPTS[v{i}];'
                     f'[0:a]atrim={x}:{y},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,afade=t=out:st={y-x-0.012:.3f}:d=0.012[a{i}]')
    parts.append(''.join(f'[v{i}][a{i}]' for i in range(len(keep))) + f'concat=n={len(keep)}:v=1:a=1[v][a]')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a.src, '-filter_complex', ';'.join(parts), '-map', '[v]', '-map', '[a]',
                    '-r', str(a.fps), '-c:v', 'libx264', '-crf', '16', '-g', str(a.fps), '-keyint_min', str(a.fps),
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', a.dst], check=True)
    print('segments:', keep)
    print(f'duration: {dur:.2f}s -> {sum(y - x for x, y in keep):.2f}s')


if __name__ == '__main__':
    main()
