# combine_obs_v2.ps1
# Combines mixed OBS/MFC recordings (MKV and/or MP4) into two outputs:
#   1. "00 Rin - Club Show - YYYY-MM-DD.mkv"             - concatenated working file (visually lossless)
#   2. "00 Rin - Club Show - YYYY-MM-DD-compressed.mp4"  - re-encoded to fit under TargetGB
#
# TargetGB defaults to 9.5 GB to stay safely under MFCShare's 10 GB per-file upload limit.
#
# v2 changes vs v1:
#   - Accepts MKV and MP4 inputs together in one run.
#   - Orders files by timestamps parsed from the FILENAME (not mtime), supporting both:
#       * RinCity_MyFreeCams_YYYYMMDD-HHMMSS.mkv
#       * Club Show - M-D-YYYY - HHMMam/pm.mp4
#     so a short MKV recorded between two club shows lands in the right spot, even across midnight.
#   - Because inputs can have different codecs/resolutions/framerates, each input is first
#     normalized (re-encoded at a visually-lossless bitrate) to a common format in a _normalized
#     subdirectory, then those intermediates are stream-copy concatenated into the working MKV.
#     The target resolution/fps is auto-detected from the highest-resolution input.
#   - NVENC is the default encoder. Pass -CPU to force libx264.
#   - Normalized intermediates are kept only if concat fails (for debugging); otherwise deleted.
#
# Usage:
#   .\combine_obs_v2.ps1
#   .\combine_obs_v2.ps1 -TargetGB 8.5
#   .\combine_obs_v2.ps1 -CPU -Preset medium
#   .\combine_obs_v2.ps1 -FFmpegDir "C:\tools\ffmpeg"
#   .\combine_obs_v2.ps1 -CompressOnly
#   .\combine_obs_v2.ps1 file1.mkv file2.mp4 file3.mkv

param(
    [string]$FFmpegDir = "",
    [double]$TargetGB = 9.5,
    [ValidateSet("ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow")]
    [string]$Preset = "slow",
    [switch]$CompressOnly,
    [switch]$CPU,
    [switch]$NVENC,   # accepted for back-compat; NVENC is the default now
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Files
)

$ErrorActionPreference = "Stop"

# --- Require PowerShell 7+ ---
# This script uses ProcessStartInfo.ArgumentList (introduced in .NET Core 2.1),
# which is not available in Windows PowerShell 5.1 (built on .NET Framework).
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Error ("This script requires PowerShell 7 or later. " +
                 "Detected: PowerShell $($PSVersionTable.PSVersion). " +
                 "Launch 'pwsh' instead of 'powershell' and re-run.")
}

# --- Resolve ffmpeg/ffprobe ---
if ($FFmpegDir) {
    $ffmpeg  = Join-Path $FFmpegDir "ffmpeg.exe"
    $ffprobe = Join-Path $FFmpegDir "ffprobe.exe"
    foreach ($bin in @($ffmpeg, $ffprobe)) {
        if (-not (Test-Path $bin)) {
            Write-Error "Not found: $bin`nCheck your -FFmpegDir path."
        }
    }
} else {
    $ffmpeg  = "ffmpeg"
    $ffprobe = "ffprobe"
    foreach ($cmd in @("ffmpeg", "ffprobe")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            Write-Error "$cmd not found in PATH. Use -FFmpegDir to specify its location."
        }
    }
}

# --- Encoder selection: NVENC default, -CPU opts out ---
if ($NVENC -and $CPU) {
    Write-Error "Cannot specify both -NVENC and -CPU."
}
$UseNVENC = -not $CPU

# --- Helper: parse a sortable timestamp out of a filename ---
# Returns a [datetime] for sorting, or $null if no pattern matched.
function Get-FilenameTimestamp {
    param([string]$Name)

    $base = [System.IO.Path]::GetFileNameWithoutExtension($Name)

    # Format A: RinCity_MyFreeCams_20260417-204926 (YYYYMMDD-HHMMSS anywhere in name)
    if ($base -match '(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})') {
        try {
            return [datetime]::new(
                [int]$Matches[1], [int]$Matches[2], [int]$Matches[3],
                [int]$Matches[4], [int]$Matches[5], [int]$Matches[6])
        } catch { return $null }
    }

    # Format B: "Club Show - 4-18-2026 - 1242am" (M-D-YYYY then HHMM[am|pm])
    if ($base -match '(\d{1,2})-(\d{1,2})-(\d{4}).*?(\d{1,2})(\d{2})\s*(am|pm)') {
        try {
            $month  = [int]$Matches[1]
            $day    = [int]$Matches[2]
            $year   = [int]$Matches[3]
            $hour12 = [int]$Matches[4]
            $minute = [int]$Matches[5]
            $ampm   = $Matches[6].ToLower()

            $hour24 = $hour12 % 12
            if ($ampm -eq "pm") { $hour24 += 12 }

            return [datetime]::new($year, $month, $day, $hour24, $minute, 0)
        } catch { return $null }
    }

    return $null
}

# --- Helper: probe a file for codec/resolution/fps ---
function Get-VideoSignature {
    param([string]$Path)

    $json = & $ffprobe -v error -print_format json `
        -show_entries "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels" `
        -- $Path 2>$null

    if (-not $json) { return $null }

    try {
        $data = ($json -join "`n") | ConvertFrom-Json
    } catch {
        return $null
    }

    $video = $data.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1
    $audio = $data.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1
    if (-not $video) { return $null }

    # Convert r_frame_rate "30000/1001" -> 29.97
    $fpsNum = 0.0
    if ($video.r_frame_rate -match '^(\d+)/(\d+)$') {
        $num = [double]$Matches[1]
        $den = [double]$Matches[2]
        if ($den -gt 0) { $fpsNum = $num / $den }
    } elseif ($video.r_frame_rate -match '^[\d.]+$') {
        $fpsNum = [double]$video.r_frame_rate
    }

    [pscustomobject]@{
        VideoCodec = $video.codec_name
        Width      = [int]$video.width
        Height     = [int]$video.height
        FrameRate  = $fpsNum
        PixFmt     = $video.pix_fmt
        AudioCodec = if ($audio) { $audio.codec_name }      else { $null }
        AudioRate  = if ($audio) { [int]$audio.sample_rate } else { 0 }
        AudioChans = if ($audio) { [int]$audio.channels }    else { 0 }
    }
}

# --- Helper: probe duration ---
function Get-DurationSeconds {
    param([string]$Path)

    $dur = & $ffprobe -v error -show_entries format=duration `
        -of default=noprint_wrappers=1:nokey=1 -- $Path 2>$null
    if (-not $dur) { return 0.0 }
    return [double]$dur
}

# --- Helper: run ffmpeg with a live Write-Progress bar ---
function Invoke-FFmpegWithProgress {
    param(
        [string]$Activity,
        [double]$TotalSeconds,
        [string[]]$FFmpegArgs
    )

    $progressFile = [System.IO.Path]::GetTempFileName()
    $allArgs = @("-y", "-progress", $progressFile, "-nostats") + $FFmpegArgs

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName           = $ffmpeg
    $psi.WorkingDirectory   = (Get-Location).Path
    $psi.UseShellExecute    = $false
    $psi.RedirectStandardError  = $false
    $psi.RedirectStandardOutput = $false
    $psi.CreateNoWindow     = $false
    foreach ($arg in $allArgs) {
        $psi.ArgumentList.Add($arg)
    }

    $process = [System.Diagnostics.Process]::Start($psi)
    $startTime = Get-Date

    while (-not $process.HasExited) {
        Start-Sleep -Milliseconds 500

        $outTimeSec = 0.0
        $speed      = 0.0
        if (Test-Path $progressFile) {
            $lines = Get-Content $progressFile -ErrorAction SilentlyContinue
            foreach ($line in $lines) {
                if ($line -match '^out_time_us=(\d+)') {
                    $outTimeSec = [double]$Matches[1] / 1000000
                }
                if ($line -match '^speed=\s*([\d.]+)x') {
                    $speed = [double]$Matches[1]
                }
            }
        }

        $elapsed = (Get-Date) - $startTime
        $pct     = if ($TotalSeconds -gt 0) { [math]::Min(99, ($outTimeSec / $TotalSeconds) * 100) } else { 0 }

        $etaStr = "calculating..."
        if ($speed -gt 0 -and $outTimeSec -gt 0) {
            $remainingSec = ($TotalSeconds - $outTimeSec) / $speed
            $eta = [timespan]::FromSeconds($remainingSec)
            $etaStr = "{0:hh\:mm\:ss}" -f $eta
        }

        $elapsedStr   = "{0:hh\:mm\:ss}" -f $elapsed
        $processedStr = "{0:hh\:mm\:ss}" -f [timespan]::FromSeconds($outTimeSec)
        $totalStr     = "{0:hh\:mm\:ss}" -f [timespan]::FromSeconds($TotalSeconds)
        $status = "$processedStr / $totalStr  ETA: $etaStr  Speed: $($speed)x  Elapsed: $elapsedStr"

        Write-Progress -Activity $Activity -Status $status -PercentComplete $pct
    }

    $process.WaitForExit()
    Write-Progress -Activity $Activity -Completed
    Remove-Item $progressFile -ErrorAction SilentlyContinue

    if ($process.ExitCode -ne 0) {
        Write-Error "ffmpeg exited with code $($process.ExitCode)."
    }
}

# --- Build encoder args for the COMPRESSED output (bitrate-targeted) ---
function Get-CompressedEncoderArgs {
    param([int]$VideoBitrateK)

    $maxrate = [math]::Floor($VideoBitrateK * 1.5)
    $bufsize = [math]::Floor($VideoBitrateK * 3)

    if ($UseNVENC) {
        return @(
            "-c:v", "h264_nvenc",
            "-b:v", "${VideoBitrateK}k",
            "-maxrate", "${maxrate}k",
            "-bufsize", "${bufsize}k",
            "-preset", "p5",
            "-rc", "vbr",
            "-spatial-aq", "1",
            "-temporal-aq", "1"
        )
    } else {
        return @(
            "-c:v", "libx264",
            "-b:v", "${VideoBitrateK}k",
            "-maxrate", "${maxrate}k",
            "-bufsize", "${bufsize}k",
            "-preset", $Preset
        )
    }
}

# --- Build encoder args for the NORMALIZED intermediate (visually lossless, quality-targeted) ---
# NVENC: CQ 18 (near-transparent); x264: CRF 18. Both are conventional "visually lossless" settings.
function Get-NormalizeEncoderArgs {
    if ($UseNVENC) {
        return @(
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-rc", "vbr",
            "-cq", "18",
            "-b:v", "0",
            "-spatial-aq", "1",
            "-temporal-aq", "1"
        )
    } else {
        return @(
            "-c:v", "libx264",
            "-preset", $Preset,
            "-crf", "18"
        )
    }
}

# --- Discover and order input files by filename timestamp ---
if (-not $CompressOnly) {
    if (-not $Files -or $Files.Count -eq 0) {
        $Files = Get-ChildItem -File | Where-Object { $_.Extension -in '.mkv', '.mp4' } |
            Select-Object -ExpandProperty FullName
    }
    if (-not $Files -or $Files.Count -eq 0) {
        Write-Error "No MKV or MP4 files found in the current directory."
    }

    # Parse timestamp for every file; fail loudly if any don't match a known pattern,
    # because guessing order across two naming conventions is worse than erroring.
    $annotated = foreach ($f in $Files) {
        $leaf = Split-Path $f -Leaf
        $ts   = Get-FilenameTimestamp -Name $leaf
        if (-not $ts) {
            Write-Error "Could not parse a timestamp from filename '$leaf'. Supported formats: 'YYYYMMDD-HHMMSS' anywhere in the name, or 'M-D-YYYY - HHMMam/pm'."
        }
        [pscustomobject]@{ Path = $f; Timestamp = $ts; Leaf = $leaf }
    }

    $ordered = $annotated | Sort-Object Timestamp
    $Files   = $ordered | Select-Object -ExpandProperty Path
}

# --- Derive show date and output names ---
if ($CompressOnly) {
    $existing = Get-ChildItem -Filter "00 Rin - Club Show - *.mkv" |
        Where-Object { $_.Name -notlike "*-compressed*" } |
        Sort-Object Name |
        Select-Object -First 1
    if (-not $existing) {
        Write-Error "No existing '00 Rin - Club Show - *.mkv' found. Run without -CompressOnly first."
    }
    $OutputMKV = $existing.FullName
    if ($existing.Name -match '(\d{4}-\d{2}-\d{2})') {
        $showDate = $Matches[1]
    } else {
        Write-Error "Could not parse date from '$($existing.Name)'."
    }
    Write-Host ""
    Write-Host "CompressOnly mode - using existing MKV: $($existing.Name)"
} else {
    # Show date = date of FIRST input (a show that starts on the 17th and bleeds past midnight
    # is still "the 17th's show"), derived from the parsed filename timestamp.
    $showDate = $ordered[0].Timestamp.ToString("yyyy-MM-dd")
    $OutputMKV = "00 Rin - Club Show - $showDate.mkv"
}

$OutputMP4 = "00 Rin - Club Show - $showDate-compressed.mp4"

Write-Host ""
if (-not $CompressOnly) {
    Write-Host "Files to combine ($($Files.Count)), in filename-timestamp order:"
    foreach ($item in $ordered) {
        Write-Host ("  {0}  [{1}]" -f $item.Leaf, $item.Timestamp.ToString("yyyy-MM-dd HH:mm:ss"))
    }
    Write-Host ""
    Write-Host "Output MKV : $OutputMKV"
}
Write-Host "Output MP4 : $OutputMP4 (targeting ${TargetGB} GB, MFCShare limit is 10 GB)"
if ($UseNVENC) {
    Write-Host "Encoder    : h264_nvenc (p5)"
} else {
    Write-Host "Encoder    : libx264 ($Preset)"
}
Write-Host ""

# --- Step 1: Normalize inputs to a common format, then concat (skipped if -CompressOnly) ---
if (-not $CompressOnly) {
    # Probe every input so we can pick a target resolution/fps
    Write-Host "Probing inputs..."
    $probes = @()
    foreach ($f in $Files) {
        $sig = Get-VideoSignature -Path $f
        if (-not $sig) {
            Write-Error "ffprobe failed on: $f"
        }
        $leaf = Split-Path $f -Leaf
        Write-Host ("  {0}: {1}x{2} @ {3:F2}fps, {4} / {5}" -f `
            $leaf, $sig.Width, $sig.Height, $sig.FrameRate, $sig.VideoCodec, $sig.AudioCodec)
        $probes += [pscustomobject]@{ Path = $f; Sig = $sig }
    }

    # Target = highest-resolution input (tiebreak: highest framerate, then largest pixel count again)
    $target = $probes |
        Sort-Object -Property @{Expression = { $_.Sig.Width * $_.Sig.Height }; Descending = $true},
                              @{Expression = { $_.Sig.FrameRate };              Descending = $true} |
        Select-Object -First 1

    $targetW   = $target.Sig.Width
    $targetH   = $target.Sig.Height
    $targetFps = $target.Sig.FrameRate
    if ($targetFps -le 0) { $targetFps = 30.0 }

    Write-Host ""
    Write-Host ("Target intermediate format: {0}x{1} @ {2:F2}fps, yuv420p, AAC 48kHz stereo" -f `
        $targetW, $targetH, $targetFps)
    Write-Host ""

    # Normalize each input into _normalized\NN_<origname>.mkv
    $normDir = Join-Path (Get-Location).Path "_normalized"
    if (Test-Path $normDir) {
        Remove-Item $normDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $normDir | Out-Null

    $normalizedFiles = @()
    $normalizeFailed = $false

    for ($i = 0; $i -lt $probes.Count; $i++) {
        $src      = $probes[$i].Path
        $srcSig   = $probes[$i].Sig
        $srcLeaf  = [System.IO.Path]::GetFileNameWithoutExtension($src)
        $idxStr   = "{0:D2}" -f ($i + 1)
        $dstName  = "${idxStr}_${srcLeaf}.mkv"
        $dst      = Join-Path $normDir $dstName

        $needsVideoTransform = ($srcSig.Width -ne $targetW) -or
                               ($srcSig.Height -ne $targetH) -or
                               ([math]::Abs($srcSig.FrameRate - $targetFps) -gt 0.01) -or
                               ($srcSig.PixFmt -ne "yuv420p") -or
                               ($srcSig.VideoCodec -ne "h264")
        $needsAudioTransform = ($srcSig.AudioCodec -ne "aac") -or
                               ($srcSig.AudioRate -ne 48000) -or
                               ($srcSig.AudioChans -ne 2)

        $durSec = Get-DurationSeconds -Path $src
        $stage  = ("Normalizing [{0}/{1}]: {2}" -f ($i + 1), $probes.Count, (Split-Path $src -Leaf))
        Write-Host $stage

        # Build filter: scale with aspect preservation + padding, then set fps + pixel format.
        # This handles the case where an input is a different aspect ratio from the target.
        $vf = "scale=${targetW}:${targetH}:force_original_aspect_ratio=decrease," +
              "pad=${targetW}:${targetH}:(ow-iw)/2:(oh-ih)/2," +
              "fps=${targetFps},format=yuv420p"

        $ffArgs = @("-i", $src, "-vf", $vf) +
                (Get-NormalizeEncoderArgs) +
                @("-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                  "-map", "0:v:0", "-map", "0:a:0?",
                  $dst)

        try {
            Invoke-FFmpegWithProgress -Activity $stage -TotalSeconds $durSec -FFmpegArgs $ffArgs
        } catch {
            Write-Warning "Normalization failed for: $src"
            $normalizeFailed = $true
            break
        }

        if (-not (Test-Path $dst)) {
            Write-Warning "Expected normalized output missing: $dst"
            $normalizeFailed = $true
            break
        }

        $normalizedFiles += $dst
    }

    if ($normalizeFailed) {
        Write-Host ""
        Write-Host "Normalization step failed. Intermediates kept in: $normDir"
        Write-Error "Aborting before concat."
    }

    # Build concat list
    $listFile  = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".txt")
    $utf8NoBOM = New-Object System.Text.UTF8Encoding $false
    $writer    = [System.IO.StreamWriter]::new($listFile, $false, $utf8NoBOM)
    foreach ($nf in $normalizedFiles) {
        $escaped = $nf.Replace("\", "/").Replace("'", "'\''")
        $writer.WriteLine("file '$escaped'")
    }
    $writer.Close()

    Write-Host ""
    Write-Host "Concatenating normalized files (stream copy) -> $OutputMKV"
    Write-Host ""

    $concatOk = $true
    try {
        & $ffmpeg -y -f concat -safe 0 -i $listFile -c copy -- $OutputMKV
        if ($LASTEXITCODE -ne 0) { $concatOk = $false }
    } catch {
        $concatOk = $false
    }

    Remove-Item $listFile -ErrorAction SilentlyContinue

    if (-not $concatOk -or -not (Test-Path $OutputMKV)) {
        Write-Host ""
        Write-Host "Concat failed. Normalized intermediates kept for inspection in: $normDir"
        Write-Error "Concat step failed."
    }

    # Success - drop the intermediates
    Remove-Item $normDir -Recurse -Force -ErrorAction SilentlyContinue

    $mkvSizeGB = [math]::Round((Get-Item $OutputMKV).Length / 1GB, 2)
    Write-Host ""
    Write-Host "Working MKV done: '$OutputMKV' ($mkvSizeGB GB)"
    Write-Host ""
} else {
    $mkvSizeGB = [math]::Round((Get-Item $OutputMKV).Length / 1GB, 2)
}

# --- Calculate duration from combined MKV ---
Write-Host "Calculating duration for bitrate targeting..."
$totalSeconds = Get-DurationSeconds -Path $OutputMKV
if ($totalSeconds -le 0) {
    Write-Error "ffprobe failed on: $OutputMKV"
}
$totalMinutes = [math]::Round($totalSeconds / 60, 1)
Write-Host "Total duration: $totalMinutes min ($([math]::Round($totalSeconds, 1)) sec)"

# --- Target bitrate calculation ---
$targetBytes    = $TargetGB * 1GB
$audioBitsTotal = 192000 * $totalSeconds
$videoBits      = ($targetBytes * 8) - $audioBitsTotal
$videoBitrateK  = [math]::Floor($videoBits / $totalSeconds / 1000)
Write-Host "Target video bitrate: ${videoBitrateK}k"
Write-Host ""

# --- Step 2: Re-encode to compressed MP4 with progress bar ---
$stepLabel = if ($CompressOnly) { "Step 1 of 1" } else { "Step 2 of 2" }
Write-Host "${stepLabel}: Encoding compressed MP4..."
Write-Host ""

$videoArgs = Get-CompressedEncoderArgs -VideoBitrateK $videoBitrateK
if ($UseNVENC) {
    Write-Host "Encoder: h264_nvenc (p5)"
} else {
    Write-Host "Encoder: libx264 ($Preset)"
}
Write-Host ""

Invoke-FFmpegWithProgress `
    -Activity "Encoding compressed MP4" `
    -TotalSeconds $totalSeconds `
    -FFmpegArgs (@(
        "-i", $OutputMKV
    ) + $videoArgs + @(
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        $OutputMP4
    ))

# --- Final report ---
if (Test-Path $OutputMP4) {
    $mp4SizeGB = [math]::Round((Get-Item $OutputMP4).Length / 1GB, 2)
    Write-Host ""
    Write-Host "All done!"
    if (-not $CompressOnly) {
        Write-Host "  MKV : '$OutputMKV' ($mkvSizeGB GB)"
    }
    Write-Host "  MP4 : '$OutputMP4' ($mp4SizeGB GB, under 10 GB MFCShare limit: $([math]::Round(10 - $mp4SizeGB, 2)) GB headroom)"
} else {
    Write-Error "MP4 output not found - ffmpeg may have failed."
}
