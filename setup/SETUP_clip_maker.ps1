<#
  SETUP_clip_maker.ps1 - one-shot setup for making documentary-style clips with Claude Code + HyperFrames
  Windows 10/11, PowerShell 5.1+.   Safe to re-run: it only installs what is missing.

  Run (normal PowerShell window):
      powershell -ExecutionPolicy Bypass -File .\SETUP_clip_maker.ps1

  Options:
      -ToolsDir <path>          where whisper.cpp / fonts / optional voice model live   (default: %USERPROFILE%\tools)
      -HyperframesVersion <v>   HyperFrames CLI version to pin                            (default: 0.8.186, the one this kit was made with)
      -SkipSkills               do not touch ~\.claude\skills (skips BOTH the HyperFrames skills and the documentary-clip skill)
      -SkillsDir <path>         where Claude Code skills live                             (default: %USERPROFILE%\.claude\skills)
      -WithLocalVoice           also install the free local Thai voice (VoxCPM2). Needs an NVIDIA GPU with 8 GB+ VRAM
      -TestKeys                 also send a tiny test request to ElevenLabs (costs ~3 characters of credit)
      -DryRun                   only print what would be done

  API keys are NEVER stored in this file. Put them in user environment variables:
      setx PIXABAY_API_KEY "..."        (free: pixabay.com/api/docs)
      setx ELEVENLABS_API_KEY "sk_..."  (free tier works for premade voices with model eleven_v3)
#>
param(
    [string]$ToolsDir = "$env:USERPROFILE\tools",
    [string]$HyperframesVersion = '0.8.186',
    [string]$SkillsDir = "$env:USERPROFILE\.claude\skills",
    [switch]$SkipSkills,
    [switch]$WithLocalVoice,
    [switch]$TestKeys,
    [switch]$DryRun
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = 'Continue'
$results = [ordered]@{}

function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Works($exe, $arg = '--version') {
    try { $o = & $exe $arg 2>&1; return ($LASTEXITCODE -eq 0 -and $o) } catch { return $false }
}
function Step($label, [scriptblock]$body) {
    Say $label
    if ($DryRun) { Write-Host '    (dry run) skipped'; $results[$label] = 'dry-run'; return }
    try { & $body; if (-not $results.Contains($label)) { $results[$label] = 'ok' } }
    catch { $results[$label] = 'FAILED: ' + $_.Exception.Message; Write-Host ('    ' + $results[$label]) -ForegroundColor Red }
}
function WingetInstall($id) {
    winget install --id $id --exact --silent --accept-package-agreements --accept-source-agreements
    # -1978335189 = "already installed / no upgrade available"
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw "winget failed for $id (exit $LASTEXITCODE)" }
    Refresh-Path
}
function Download($url, $dest) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -UserAgent 'Mozilla/5.0 clip-maker-setup'
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host 'winget not found. Install "App Installer" from the Microsoft Store, then run this again.' -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

# ---------------------------------------------------------------- base tools
Step 'Git' { if (-not (Works git)) { WingetInstall 'Git.Git' } else { $results['Git'] = 'already installed' } }
Step 'Node.js (20+)' {
    $major = 0
    try { $major = [int]((node --version) -replace '^v(\d+).*', '$1') } catch {}
    if ($major -lt 20) { WingetInstall 'OpenJS.NodeJS.LTS' } else { $results['Node.js (20+)'] = "already installed (v$major)" }
}
Step 'Python 3' { if (-not (Works python)) { WingetInstall 'Python.Python.3.13' } else { $results['Python 3'] = 'already installed' } }
Step 'FFmpeg' { if (-not (Works ffmpeg '-version')) { WingetInstall 'Gyan.FFmpeg' } else { $results['FFmpeg'] = 'already installed' } }
Refresh-Path

Step 'Python packages (yt-dlp, pythainlp, edge-tts, numpy, soundfile)' {
    python -m pip install --upgrade --quiet yt-dlp pythainlp edge-tts numpy soundfile
    if ($LASTEXITCODE -ne 0) { throw 'pip failed' }
}

# ---------------------------------------------------------------- HyperFrames (renders HTML to video)
Step "HyperFrames CLI $HyperframesVersion" {
    $have = ''
    try { $have = (hyperframes --version 2>$null | Select-Object -Last 1).Trim() } catch {}
    if ($have -ne $HyperframesVersion) {
        npm install -g "hyperframes@$HyperframesVersion"
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
        Refresh-Path
    } else { $results["HyperFrames CLI $HyperframesVersion"] = 'already installed' }
}
if (-not $SkipSkills) {
    Step 'HyperFrames skills for Claude Code (~\.claude\skills)' {
        hyperframes skills update
        if ($LASTEXITCODE -ne 0) { throw 'skills update failed' }
    }
}

if (-not $SkipSkills) {
    Step 'documentary-clip skill (from this repo)' {
        $src = Join-Path $PSScriptRoot '..\skills\documentary-clip'
        if (-not (Test-Path (Join-Path $src 'SKILL.md'))) { throw "skill folder not found next to this script: $src" }
        New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
        $dst = Join-Path $SkillsDir 'documentary-clip'
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse -Force $src $dst
    }
}

# ---------------------------------------------------------------- speech-to-text (word timings / captions)
Step 'whisper.cpp (speech to text)' {
    $exe = Join-Path $ToolsDir 'whisper-cpp\Release\whisper-cli.exe'
    if (-not (Test-Path $exe)) {
        $zip = Join-Path $env:TEMP 'whisper-bin-x64.zip'
        Download 'https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip' $zip
        Expand-Archive -Force -Path $zip -DestinationPath (Join-Path $ToolsDir 'whisper-cpp')
        Remove-Item $zip -Force
    } else { $results['whisper.cpp (speech to text)'] = 'already installed' }
    if (-not (Test-Path $exe)) { throw "whisper-cli.exe not found at $exe" }
    [Environment]::SetEnvironmentVariable('HYPERFRAMES_WHISPER_PATH', $exe, 'User')   # HyperFrames looks here
    $env:HYPERFRAMES_WHISPER_PATH = $exe
}

# ---------------------------------------------------------------- Thai fonts used by the clips (SIL OFL)
Step 'Thai fonts (Trirong, Kanit)' {
    $dir = Join-Path $ToolsDir 'fonts'
    $base = 'https://github.com/google/fonts/raw/main/ofl'
    foreach ($f in 'trirong/Trirong-Regular', 'trirong/Trirong-SemiBold', 'trirong/Trirong-Bold', 'kanit/Kanit-Bold') {
        $dest = Join-Path $dir ((Split-Path $f -Leaf) + '.ttf')
        if (-not (Test-Path $dest)) { Download "$base/$f.ttf" $dest }
    }
}

# ---------------------------------------------------------------- optional: free local Thai voice
if ($WithLocalVoice) {
    Step 'Local Thai voice (VoxCPM2, needs NVIDIA GPU 8 GB+)' {
        if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw 'No NVIDIA GPU / driver found (nvidia-smi missing)' }
        if (-not (Works uv)) { WingetInstall 'astral-sh.uv' }
        $tts = Join-Path $ToolsDir 'tts'
        New-Item -ItemType Directory -Force -Path $tts | Out-Null
        $env:UV_CACHE_DIR = Join-Path $tts 'uv-cache'; $env:UV_LINK_MODE = 'copy'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $tts 'python'
        [Environment]::SetEnvironmentVariable('HF_HOME', (Join-Path $tts 'hf'), 'User')
        uv python install 3.11
        uv venv --python 3.11 (Join-Path $tts 'venv')
        $py = Join-Path $tts 'venv\Scripts\python.exe'
        # torch 2.8 + CUDA 12.8 is the build that works on RTX 50-series (sm_120); keep it pinned
        uv pip install --python $py torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
        "torch==2.8.0+cu128`ntorchaudio==2.8.0+cu128" | Set-Content (Join-Path $tts 'pin.txt')
        uv pip install --python $py voxcpm numpy soundfile --constraint (Join-Path $tts 'pin.txt') --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
        & $py -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available())"
    }
}

# ---------------------------------------------------------------- checks
Say 'Checking'
$sys = (Get-Item $env:TEMP).PSDrive
if ($sys.Free -lt 6GB) {
    Write-Host ('    WARNING: only {0:N1} GB free on {1}: . A render needs ~1-2 GB of temp space. Point TEMP/TMP at a drive with more room before rendering.' -f ($sys.Free / 1GB), $sys.Name) -ForegroundColor Yellow
}
$keys = [ordered]@{ PIXABAY_API_KEY = 'free stock video/photos'; ELEVENLABS_API_KEY = 'ElevenLabs voice-over' }
foreach ($k in $keys.Keys) {
    if ([Environment]::GetEnvironmentVariable($k, 'User')) { Write-Host "    $k is set" } else { Write-Host "    $k NOT set ($($keys[$k])):  setx $k `"...`"" -ForegroundColor Yellow }
}
if (-not $DryRun) {
    $pix = [Environment]::GetEnvironmentVariable('PIXABAY_API_KEY', 'User')
    if ($pix) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -UserAgent 'Mozilla/5.0' -Uri "https://pixabay.com/api/?key=$pix&q=test&per_page=3"
            Write-Host "    Pixabay key works (HTTP $($r.StatusCode))" -ForegroundColor Green
        } catch { Write-Host "    Pixabay key test FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    }
    $el = [Environment]::GetEnvironmentVariable('ELEVENLABS_API_KEY', 'User')
    if ($el) {
        try {
            $s = Invoke-RestMethod -Uri 'https://api.elevenlabs.io/v1/user/subscription' -Headers @{ 'xi-api-key' = $el }
            Write-Host "    ElevenLabs key accepted: tier=$($s.tier), used $($s.character_count)/$($s.character_limit) characters" -ForegroundColor Green
            if ($TestKeys) {
                try {
                    $body = '{"text":"ok","model_id":"eleven_v3"}'
                    Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'https://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb' -Headers @{ 'xi-api-key' = $el } -ContentType 'application/json' -Body $body -OutFile (Join-Path $env:TEMP 'el_test.mp3')
                    Write-Host '    ElevenLabs text-to-speech works' -ForegroundColor Green
                } catch { Write-Host "    ElevenLabs text-to-speech FAILED: $($_.Exception.Message)" -ForegroundColor Red }
            }
        } catch { Write-Host "    ElevenLabs key test FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    }
    Write-Host ''
    hyperframes doctor 2>&1 | Select-String -Pattern 'Node|FFmpeg|FFprobe|Chrome|whisper|Version' | ForEach-Object { '    ' + $_.Line.Trim() }
}

Write-Host ''
Write-Host '================ SUMMARY ================' -ForegroundColor Cyan
foreach ($k in $results.Keys) {
    $c = if ($results[$k] -like 'FAILED*') { 'Red' } else { 'Green' }
    Write-Host ('{0,-58} {1}' -f $k, $results[$k]) -ForegroundColor $c
}
Write-Host ''
Write-Host 'Next: restart Claude Code (so the new skills load), set your API keys (see README), then ask it to make a clip.'
