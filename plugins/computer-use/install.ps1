param(
    [string]$WorkspacePath = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($WorkspacePath) {
    $TargetDir = Join-Path (Resolve-Path $WorkspacePath).Path ".agents\plugins\computer-use"
} else {
    $TargetDir = Join-Path $env:USERPROFILE ".gemini\config\plugins\computer-use"
}

Write-Host "=== Fast Computer Use Plugin Kurulumu ===" -ForegroundColor Cyan
Write-Host "Hedef klasor: $TargetDir"

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
foreach ($item in @("plugin.json", "README.md", "requirements.txt", "install.ps1", "install.bat", "assets", "rules", "skills", "server")) {
    $src = Join-Path $SourceRoot $item
    $dst = Join-Path $TargetDir $item
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item $src $dst -Recurse -Force
}

$VenvDir = Join-Path $TargetDir ".venv"
if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Host "Python sanal ortami (.venv) olusturuluyor..." -ForegroundColor Cyan
    python -m venv $VenvDir
}

$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip -q
& $VenvPy -m pip install -r (Join-Path $TargetDir "requirements.txt") -q

$VenvPySlash = $VenvPy -replace "\\", "/"
$McpJson = @"
{
  "mcpServers": {
    "desktop": {
      "command": "$VenvPySlash",
      "args": [
        "`${PLUGIN_ROOT}/server/computer_use_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "COMPUTER_USE_DATA_DIR": "`${PLUGIN_DATA}"
      }
    }
  }
}
"@
Set-Content -Path (Join-Path $TargetDir "mcp_config.json") -Value $McpJson -Encoding UTF8

if (-not $SkipTests) {
    $env:PYTHONPATH = Join-Path $TargetDir "server"
    & $VenvPy -m pytest (Join-Path $TargetDir "server\tests\test_computer_use.py") -v
}

Write-Host "`n[OK] Fast Computer Use plugin kuruldu! Antigravity'yi yeniden baslatin." -ForegroundColor Green
