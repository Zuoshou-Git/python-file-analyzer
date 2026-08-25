$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --clean FileAnalyzer.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }
    Write-Host "构建完成：$PSScriptRoot\dist\FileAnalyzer.exe"
}
finally {
    Pop-Location
}
