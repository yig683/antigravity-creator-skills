param(
    [switch]$WithGpuTts
)

$ErrorActionPreference = "Stop"
$EngineDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[MakineStudio] Core Python paketleri kuruluyor..." -ForegroundColor Cyan
python -m pip install --upgrade -r (Join-Path $EngineDir "requirements.txt")

if ($WithGpuTts) {
    Write-Host "[MakineStudio] Yerel GPU Chatterbox TTS (.venv_tts) kuruluyor..." -ForegroundColor Cyan
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "[MakineStudio] 'uv' bulunamadi, pip ile yukleniyor..." -ForegroundColor Yellow
        python -m pip install uv
    }
    $VenvDir = Join-Path $EngineDir ".venv_tts"
    uv venv $VenvDir --python 3.11
    $VenvPy = Join-Path $VenvDir "Scripts\python.exe"
    uv pip install --python $VenvPy "torch==2.6.0+cu124" "torchaudio==2.6.0+cu124" --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python $VenvPy chatterbox-tts
    Write-Host "[MakineStudio] GPU TTS ortami hazir -> $VenvPy" -ForegroundColor Green
} else {
    Write-Host "[MakineStudio] Not: Edge-TTS varsayilan olarak hazir. Yerel NVIDIA GPU seslendirme icin '-WithGpuTts' ile calistirabilirsiniz." -ForegroundColor DarkGray
}
