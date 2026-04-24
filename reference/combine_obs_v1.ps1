# combine_obs.ps1
# Creates two output files from OBS MKV recordings:
#   1. "00 Rin - Club Show - YYYY-MM-DD.mkv"             - lossless stream-copy concat
#   2. "00 Rin - Club Show - YYYY-MM-DD-compressed.mp4"  - re-encoded to fit under TargetGB
#
# Usage:
#   .\combine_obs.ps1
#   .\combine_obs.ps1 -Preset medium
#   .\combine_obs.ps1 -TargetGB 8.5
#   .\combine_obs.ps1 -FFmpegDir "C:\tools\ffmpeg"
#   .\combine_obs.ps1 -CompressOnly                      - skip concat, encode MP4 from existing MKV
#   .\combine_obs.ps1 -NVENC                              - use GPU encoder (faster, good for long files)
#   .\combine_obs.ps1 -CompressOnly -NVENC -Preset medium - combine flags freely
#   .\combine_obs.ps1 file1.mkv file2.mkv file3.mkv

param(
    [string]$FFmpegDir = "",
    [double]$TargetGB = 9.5,
    [ValidateSet("ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow")]
    [string]$Preset = "slow",
    [switch]$CompressOnly,
    [switch]$NVENC,
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

# --- Helper: run ffmpeg with a live Write-Progress bar ---
function Invoke-FFmpegWithProgress {
    param(
        [string]$Activity,
        [double]$TotalSeconds,
        [string[]]$FFmpegArgs
    )

    # Progress file ffmpeg will write to
    $progressFile = [System.IO.Path]::GetTempFileName()

    # Insert -progress and -nostats into args
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

        # Parse the progress file ffmpeg keeps overwriting
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

        $elapsedStr  = "{0:hh\:mm\:ss}" -f $elapsed
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

# --- Discover and sort files (not needed for CompressOnly) ---
if (-not $CompressOnly) {
    if (-not $Files -or $Files.Count -eq 0) {
        $Files = Get-ChildItem -Filter "*.mkv" |
            Sort-Object Name |
            Select-Object -ExpandProperty FullName
    }
    if ($Files.Count -eq 0) {
        Write-Error "No MKV files found in the current directory."
    }
}

# --- Parse date and derive output names ---
if ($CompressOnly) {
    # Find the existing combined MKV
    $existing = Get-ChildItem -Filter "00 Rin - Club Show - *.mkv" |
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
    $firstName = [System.IO.Path]::GetFileNameWithoutExtension($Files[0])
    if ($firstName -match '^(\d{4}-\d{2}-\d{2})') {
        $showDate = $Matches[1]
    } else {
        Write-Warning "Could not parse date from filename '$firstName', using today's date."
        $showDate = Get-Date -Format "yyyy-MM-dd"
    }
    $OutputMKV = "00 Rin - Club Show - $showDate.mkv"
}

$OutputMP4 = "00 Rin - Club Show - $showDate-compressed.mp4"

Write-Host ""
if (-not $CompressOnly) {
    Write-Host "Files to combine ($($Files.Count)):"
    $Files | ForEach-Object { Write-Host "  $(Split-Path $_ -Leaf)" }
    Write-Host ""
    Write-Host "Output MKV : $OutputMKV"
}
Write-Host "Output MP4 : $OutputMP4"
Write-Host "Target     : ${TargetGB} GB"
if ($NVENC) {
    Write-Host "Encoder    : h264_nvenc (p5)"
} else {
    Write-Host "Encoder    : libx264 ($Preset)"
}
Write-Host ""

# --- Step 1: Lossless concat to MKV (skipped if -CompressOnly) ---
if (-not $CompressOnly) {
    # Build concat list
    $listFile  = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".txt")
    $utf8NoBOM = New-Object System.Text.UTF8Encoding $false
    $writer    = [System.IO.StreamWriter]::new($listFile, $false, $utf8NoBOM)
    foreach ($f in $Files) {
        $escaped = $f.Replace("\", "/").Replace("'", "'\''")
        $writer.WriteLine("file '$escaped'")
    }
    $writer.Close()

    Write-Host "Step 1 of 2: Concatenating to MKV (stream copy)..."
    Write-Host ""

    & $ffmpeg -f concat -safe 0 -i $listFile -c copy $OutputMKV

    Remove-Item $listFile -ErrorAction SilentlyContinue

    if (-not (Test-Path $OutputMKV)) {
        Write-Error "MKV output not found - ffmpeg may have failed."
    }
    $mkvSizeGB = [math]::Round((Get-Item $OutputMKV).Length / 1GB, 2)
    Write-Host ""
    Write-Host "MKV done: '$OutputMKV' ($mkvSizeGB GB)"
    Write-Host ""
} else {
    $mkvSizeGB = [math]::Round((Get-Item $OutputMKV).Length / 1GB, 2)
}

# --- Calculate duration from combined MKV ---
Write-Host "Calculating duration for bitrate targeting..."
$dur = & $ffprobe -v error -show_entries format=duration `
    -of default=noprint_wrappers=1:nokey=1 $OutputMKV 2>$null
if (-not $dur) {
    Write-Error "ffprobe failed on: $OutputMKV"
}
$totalSeconds = [double]$dur
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

if ($NVENC) {
    $videoArgs = @(
        "-c:v", "h264_nvenc",
        "-b:v", "${videoBitrateK}k",
        "-maxrate", "$([math]::Floor($videoBitrateK * 1.5))k",
        "-bufsize", "$([math]::Floor($videoBitrateK * 3))k",
        "-preset", "p5",
        "-rc", "vbr",
        "-spatial-aq", "1",
        "-temporal-aq", "1"
    )
    Write-Host "Encoder: h264_nvenc (p5)"
} else {
    $videoArgs = @(
        "-c:v", "libx264",
        "-b:v", "${videoBitrateK}k",
        "-maxrate", "$([math]::Floor($videoBitrateK * 1.5))k",
        "-bufsize", "$([math]::Floor($videoBitrateK * 3))k",
        "-preset", $Preset
    )
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
    Write-Host "  MP4 : '$OutputMP4' ($mp4SizeGB GB)"
} else {
    Write-Error "MP4 output not found - ffmpeg may have failed."
}
