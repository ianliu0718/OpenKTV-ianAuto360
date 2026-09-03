<#
.SYNOPSIS
    Convert an existing KTV MP4 to H.264, up to 1080p.

.DESCRIPTION
    Write a temporary output beside the song and replace the source only after success.
    Re-encode the audio stream with the shared -14 LUFS / -1 dBTP target.

.PARAMETER InputFile
    Existing MP4 song path.

.EXAMPLE
    .\optimize_existing_video.ps1 -InputFile ".\ktv_songs\我甘願重新愛過-洋蔥 Feat.狗柏.mp4"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$InputFile
)

$ErrorActionPreference = 'Stop'
$resolvedInput = (Resolve-Path $InputFile).Path
$ffmpeg = Join-Path $PSScriptRoot 'ffmpeg\bin\ffmpeg.exe'
if (-not (Test-Path $ffmpeg)) {
    $ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ffmpegCommand) {
        $ffmpeg = $ffmpegCommand.Source
    } else {
        throw 'FFmpeg was not found.'
    }
}

$extension = [IO.Path]::GetExtension($resolvedInput)
$directory = [IO.Path]::GetDirectoryName($resolvedInput)
$baseName = [IO.Path]::GetFileNameWithoutExtension($resolvedInput)
$tempName = '{0}.optimized{1}' -f $baseName, $extension
$tempOutput = Join-Path $directory $tempName
$videoFilter = "scale=w='min(1920,iw)':h=-2:force_original_aspect_ratio=decrease"

try {
    & $ffmpeg -y -i $resolvedInput -map 0:v:0 -map '0:a?' -vf $videoFilter -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -af 'loudnorm=I=-14:TP=-1:LRA=11' -c:a aac -movflags +faststart $tempOutput
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tempOutput)) {
        throw 'FFmpeg conversion failed.'
    }
    Move-Item $tempOutput $resolvedInput -Force
    Write-Host ('Optimized: {0}' -f $resolvedInput) -ForegroundColor Green
}
finally {
    if (Test-Path $tempOutput) {
        Remove-Item $tempOutput -Force -ErrorAction SilentlyContinue
    }
}
