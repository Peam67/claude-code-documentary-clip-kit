<#
  preflight.ps1 - look at THIS machine BEFORE downloading anything.

  Prints: what is already installed, free disk space (install drive, TEMP drive), RAM / commit memory, GPU + VRAM,
  how much would still have to be downloaded for the chosen voice option, and OK / WARN / BLOCK verdicts.
  Changes nothing. Safe to run any time.

      powershell -ExecutionPolicy Bypass -File preflight.ps1 [-Voice api|voicestudio|none] [-ClipSeconds 60] [-ToolsDir D:\tools] [-Json]

  -Voice  api          ElevenLabs voice-over through the API (nothing to download; needs your key)
          voicestudio  VoiceStudio, a free open-source app that makes voices on your own PC (about 10 GB, per its own docs)
          none         no voice-over tools (you bring your own audio)
  -Json   machine-readable result (for Claude Code to read and show to the user)

  Sizes are in GB = 1024^3 bytes. They were MEASURED on the machine this kit was made on (Windows 11, RTX 5060 Ti 8 GB),
  except the VoiceStudio row, which is the figure from VoiceStudio's own Windows install guide ("~10 GB free disk"), not measured.
#>
param(
    [ValidateSet('api', 'voicestudio', 'none')][string]$Voice = 'api',
    [string]$ToolsDir = "$env:USERPROFILE\tools",
    [int]$ClipSeconds = 60,
    [switch]$Json
)

$ErrorActionPreference = 'SilentlyContinue'
function Round($x, $n = 1) { [math]::Round([double]$x, $n) }
function Works($exe, $arg = '--version') { try { $o = & $exe $arg 2>&1; return ($LASTEXITCODE -eq 0 -and [bool]$o) } catch { return $false } }
function DriveOf($path) {
    $root = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($path))
    $d = Get-PSDrive -Name $root.Substring(0, 1)
    [pscustomobject]@{ Name = $root.Substring(0, 2); FreeGB = (Round ($d.Free / 1GB)); TotalGB = (Round (($d.Used + $d.Free) / 1GB) 0) }
}

# ------------------------------------------------------------------ component sizes (installed size on disk, GB)
$VS = 'VoiceStudio app + its Python env + voice model (est. from its docs)'
$size = [ordered]@{
    'Git'                                   = 0.40
    'Node.js'                               = 0.11
    'Python 3 + yt-dlp, pythainlp, edge-tts, numpy, soundfile' = 0.33
    'FFmpeg (full build)'                   = 0.65
    'HyperFrames CLI'                       = 0.09
    'Chrome headless shell (renderer)'      = 0.26
    'whisper.cpp'                           = 0.02
    'Whisper model "medium" (Thai captions)' = 1.43
}
$size[$VS] = 10.0

# ------------------------------------------------------------------ what is already here
$chromeDir = Join-Path $env:USERPROFILE '.cache\hyperframes\chrome'
$wModel = Join-Path $env:USERPROFILE '.cache\hyperframes\whisper\models\ggml-medium.bin'
$wExe = if ($env:HYPERFRAMES_WHISPER_PATH) { $env:HYPERFRAMES_WHISPER_PATH } else { Join-Path $ToolsDir 'whisper-cpp\Release\whisper-cli.exe' }
$nodeMajor = 0; try { $nodeMajor = [int]((node --version) -replace '^v(\d+).*', '$1') } catch {}
$vsInstalled = [bool](Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs') -Directory -Filter 'VoiceStudio*' -ErrorAction SilentlyContinue)
$have = [ordered]@{
    'Git'                                   = (Works git)
    'Node.js'                               = ($nodeMajor -ge 20)
    'Python 3 + yt-dlp, pythainlp, edge-tts, numpy, soundfile' = ((Works python) -and (Works yt-dlp))
    'FFmpeg (full build)'                   = (Works ffmpeg '-version')
    'HyperFrames CLI'                       = (Works hyperframes)
    'Chrome headless shell (renderer)'      = (Test-Path $chromeDir)
    'whisper.cpp'                           = (Test-Path $wExe)
    'Whisper model "medium" (Thai captions)' = (Test-Path $wModel)
}
$have[$VS] = $vsInstalled
$wanted = New-Object System.Collections.ArrayList
foreach ($k in $size.Keys) { if ($k -ne $VS) { [void]$wanted.Add($k) } }
if ($Voice -eq 'voicestudio') { [void]$wanted.Add($VS) }

$rows = foreach ($k in $size.Keys) {
    $need = $wanted -contains $k
    [pscustomobject]@{ Component = $k; SizeGB = $size[$k]; Installed = $have[$k]; Needed = $need; ToDownloadGB = $(if ($need -and -not $have[$k]) { $size[$k] } else { 0 }) }
}
$toDownload = Round (($rows | Measure-Object ToDownloadGB -Sum).Sum)
$sizeAll = Round (($rows | Where-Object Needed | Measure-Object SizeGB -Sum).Sum)

# ------------------------------------------------------------------ machine
$os = Get-CimInstance Win32_OperatingSystem
$ramTotal = Round ($os.TotalVisibleMemorySize / 1MB); $ramFree = Round ($os.FreePhysicalMemory / 1MB); $commitFree = Round ($os.FreeVirtualMemory / 1MB)
$gpu = $null
try {
    $g = (& nvidia-smi '--query-gpu=name,memory.total,driver_version' '--format=csv,noheader,nounits' 2>$null) | Select-Object -First 1
    if ($g) { $p = $g -split ',\s*'; $gpu = [pscustomobject]@{ Name = $p[0]; VramGB = (Round ([double]$p[1] / 1024)); Driver = $p[2] } }
} catch {}
$tempDir = if ($env:TEMP) { $env:TEMP } else { 'C:\Windows\Temp' }
$dInstall = DriveOf $ToolsDir
$dTemp = DriveOf $tempDir

# render temp space: measured 1030.8 MB of frames for a 49.6 s 1080p30 clip = 0.0207 GB per second (4 workers)
$perSec = 0.0207
$renderMin = Round ($perSec * $ClipSeconds + 1.0)
$renderRec = Round ([math]::Max(5.0, 2 * $perSec * $ClipSeconds + 2.0))

# ------------------------------------------------------------------ verdicts
$checks = New-Object System.Collections.ArrayList
function Add-Check($level, $text) { [void]$checks.Add([pscustomobject]@{ Level = $level; Text = $text }) }

$needTotal = $toDownload + 2.0
if ($dInstall.FreeGB -lt $toDownload + 1) { Add-Check 'BLOCK' "Install drive $($dInstall.Name) has $($dInstall.FreeGB) GB free but $toDownload GB must be downloaded/installed. Free space, or choose another drive with -ToolsDir D:\tools." }
elseif ($dInstall.FreeGB -lt $needTotal + 3) { Add-Check 'WARN' "Install drive $($dInstall.Name) has $($dInstall.FreeGB) GB free for a $toDownload GB install - tight. Consider -ToolsDir on a roomier drive." }
else { Add-Check 'OK' "Install drive $($dInstall.Name): $($dInstall.FreeGB) GB free, $toDownload GB to download." }

if ($dTemp.FreeGB -lt $renderMin) { Add-Check 'BLOCK' "TEMP drive $($dTemp.Name) has $($dTemp.FreeGB) GB free; a $ClipSeconds s render needs >= $renderMin GB of temporary frames. Set TEMP and TMP to a roomier drive (e.g. `$env:TEMP='D:\tmp'; `$env:TMP='D:\tmp'`) before rendering." }
elseif ($dTemp.FreeGB -lt $renderRec) { Add-Check 'WARN' "TEMP drive $($dTemp.Name) has $($dTemp.FreeGB) GB free; recommended $renderRec GB free while rendering a $ClipSeconds s clip (minimum $renderMin GB)." }
else { Add-Check 'OK' "TEMP drive $($dTemp.Name): $($dTemp.FreeGB) GB free (render of $ClipSeconds s needs >= $renderMin GB, recommended $renderRec GB)." }

if ($Voice -eq 'voicestudio') {
    if (-not $gpu) { Add-Check 'WARN' 'No NVIDIA GPU found: VoiceStudio will run on the CPU (slower). ElevenLabs (-Voice api) is the easier choice.' }
    elseif ($gpu.VramGB -lt 3) { Add-Check 'WARN' "VoiceStudio's default engine (OmniVoice) used ~2 GB of VRAM when measured (its docs state a 6 GB floor); this GPU has only $($gpu.VramGB) GB, so expect it to be slow." }
    elseif ($gpu.VramGB -lt 6) { Add-Check 'INFO' "VoiceStudio docs state a 6 GB VRAM floor for its default engine, but it used only ~2 GB on an RTX 5060 Ti; this GPU has $($gpu.VramGB) GB, probably fine." }
    if ($commitFree -lt 8) { Add-Check 'WARN' "Only $commitFree GB of memory+pagefile is free. Loading voice models can fail ('The paging file is too small'). Close heavy apps (video editors, browsers) first." }
    Add-Check 'INFO' 'The ~10 GB for VoiceStudio is the number from its own install guide, not something this kit measured.'
}
if ($nodeMajor -lt 20 -and -not $have['Node.js']) { Add-Check 'INFO' 'Node.js 20+ will be installed (an existing newer Node is never replaced).' }
if ((Get-Location).Path.Length -gt 100) { Add-Check 'WARN' "Working folder path is long ($((Get-Location).Path.Length) chars). Very long folders break some tools on Windows - use a short path such as D:\clips\topic." }
foreach ($k in 'PIXABAY_API_KEY', 'ELEVENLABS_API_KEY') {
    if (-not [Environment]::GetEnvironmentVariable($k, 'User')) {
        if ($k -eq 'ELEVENLABS_API_KEY' -and $Voice -ne 'api') { continue }
        Add-Check 'INFO' "$k is not set (the user must create it; see README)."
    }
}
$verdict = if ($checks | Where-Object Level -eq 'BLOCK') { 'BLOCK' } elseif ($checks | Where-Object Level -eq 'WARN') { 'WARN' } else { 'OK' }

$result = [pscustomobject]@{
    Voice = $Voice; Verdict = $verdict; ToDownloadGB = $toDownload; TotalSelectedGB = $sizeAll
    InstallDrive = $dInstall; TempDrive = $dTemp; Ram = [pscustomobject]@{ TotalGB = $ramTotal; FreeGB = $ramFree; CommitFreeGB = $commitFree }
    Gpu = $gpu; RenderTempGB = [pscustomobject]@{ Minimum = $renderMin; Recommended = $renderRec; ForSeconds = $ClipSeconds }
    Components = $rows; Checks = $checks
}
if ($Json) { $result | ConvertTo-Json -Depth 6; return }

Write-Host ''
Write-Host "PREFLIGHT  (voice option: $Voice, clip length for render estimate: $ClipSeconds s)" -ForegroundColor Cyan
Write-Host ('  OS: {0}   RAM: {1} GB total, {2} GB free   memory+pagefile free: {3} GB' -f $os.Caption, $ramTotal, $ramFree, $commitFree)
if ($gpu) { Write-Host ('  GPU: {0}  {1} GB VRAM  driver {2}' -f $gpu.Name, $gpu.VramGB, $gpu.Driver) } else { Write-Host '  GPU: no NVIDIA GPU detected' }
Write-Host ('  Install drive {0} free {1} GB   TEMP drive {2} free {3} GB' -f $dInstall.Name, $dInstall.FreeGB, $dTemp.Name, $dTemp.FreeGB)
Write-Host ''
Write-Host ('  {0,-68} {1,8} {2,-10} {3}' -f 'Component', 'Size GB', 'On this PC', 'To download')
foreach ($r in $rows) {
    if (-not $r.Needed) { continue }
    Write-Host ('  {0,-68} {1,8} {2,-10} {3}' -f $r.Component, $r.SizeGB, $(if ($r.Installed) { 'yes' } else { 'no' }), $(if ($r.ToDownloadGB -gt 0) { "$($r.ToDownloadGB) GB" } else { '-' }))
}
Write-Host ('  {0,-68} {1,8}              {2} GB' -f 'TOTAL for the selected options', $sizeAll, $toDownload) -ForegroundColor Cyan
Write-Host ''
Write-Host "  While rendering a $ClipSeconds s clip keep >= $renderRec GB free on the TEMP drive (minimum $renderMin GB)." -ForegroundColor Cyan
Write-Host ''
foreach ($c in $checks) {
    $col = switch ($c.Level) { 'BLOCK' { 'Red' } 'WARN' { 'Yellow' } 'OK' { 'Green' } default { 'Gray' } }
    Write-Host ('  [{0,-5}] {1}' -f $c.Level, $c.Text) -ForegroundColor $col
}
Write-Host ''
Write-Host "  Verdict: $verdict" -ForegroundColor $(switch ($verdict) { 'BLOCK' { 'Red' } 'WARN' { 'Yellow' } default { 'Green' } })
if ($verdict -eq 'BLOCK') { exit 2 } elseif ($verdict -eq 'WARN') { exit 1 } else { exit 0 }
