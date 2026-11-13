param(
    [string]$WorkspacePath = "",
    [switch]$WithGpuTts,
    [switch]$SkipPythonDeps
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($WorkspacePath) {
    $TargetDir = Join-Path (Resolve-Path $WorkspacePath).Path ".agents\plugins\makine-studio"
} else {
    $TargetDir = Join-Path $env:USERPROFILE ".gemini\config\plugins\makine-studio"
}

Write-Host "=== Makine Studio Plugin Kurulumu ===" -ForegroundColor Cyan
Write-Host "Hedef klasor: $TargetDir"

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$CopyItems = @("plugin.json", "README.md", "install.ps1", "install.bat", "assets", "rules", "skills", "engine")
foreach ($item in $CopyItems) {
    $src = Join-Path $SourceRoot $item
    $dst = Join-Path $TargetDir $item
    if (Test-Path $dst) {
        if ($item -eq "engine" -and (Test-Path (Join-Path $dst ".venv_tts"))) {
            # Mevcut .venv_tts kurulumunu koruyarak engine kodlarini guncelle
            foreach ($sub in @("studio", "episodes", "assets", "requirements.txt", "setup_env.ps1")) {
                $sSub = Join-Path $src $sub
                $dSub = Join-Path $dst $sub
                if (Test-Path $dSub) { Remove-Item $dSub -Recurse -Force }
                Copy-Item $sSub $dSub -Recurse -Force
            }
            continue
        }
        Remove-Item $dst -Recurse -Force
    }
    Copy-Item $src $dst -Recurse -Force
}

if (-not $SkipPythonDeps) {
    $SetupScript = Join-Path $TargetDir "engine\setup_env.ps1"
    if ($WithGpuTts) {
        & $SetupScript -WithGpuTts
    } else {
        & $SetupScript
    }
}

Write-Host "`n=== Sistem Kontrolleri ===" -ForegroundColor Cyan
$hasFfmpeg = [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
$hasBlender = [bool](Get-Command blender -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\Blender Foundation\Blender *\blender.exe")
Write-Host ("Python  : " + (Get-Command python -ErrorAction SilentlyContinue).Source)
Write-Host ("FFmpeg  : " + $(if ($hasFfmpeg) { "OK" } else { "EKSIK (winget install Gyan.FFmpeg)" }))
Write-Host ("Blender : " + $(if ($hasBlender) { "OK" } else { "EKSIK (blender.org'dan 4.2+ / 5.x kurun)" }))

$PyTestEngine = Join-Path $TargetDir "engine"
$env:PYTHONPATH = $PyTestEngine
python -m studio.pipeline --help | Out-Null
Write-Host "`n[OK] Makine Studio plugin basariyla kuruldu!" -ForegroundColor Green
Write-Host "Antigravity'yi yeniden yuklediginizde 'makine-studio' eklentisi aktif olacaktir." -ForegroundColor Green
