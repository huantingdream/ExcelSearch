param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildEnvironment = Join-Path $projectRoot ".venv-build"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
$releaseDirectory = Join-Path $projectRoot "release"
$portableArchive = Join-Path $releaseDirectory "ExcelSearch-Windows-x64.zip"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot ".pyinstaller-cache"

Push-Location $projectRoot
try {
    if (-not (Test-Path $buildPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.12 -m venv $buildEnvironment
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv $buildEnvironment
        }
        else {
            throw "未找到 Python。请安装 64 位 Python 3.12 后重新运行。"
        }
    }

    & $buildPython -m pip install --upgrade pip
    & $buildPython -m pip install -e ".[dev,build]"

    if (-not $SkipTests) {
        & $buildPython -m pytest
    }

    & $buildPython -m PyInstaller --noconfirm --clean ExcelSearch.spec

    try {
        $env:EXCELSEARCH_DATA_DIR = Join-Path $projectRoot "build\smoke-data"
        $env:EXCELSEARCH_SMOKE_TEST = "1"
        & (Join-Path $projectRoot "dist\ExcelSearch\ExcelSearch.exe")
        if ($LASTEXITCODE -ne 0) {
            throw "打包后的 ExcelSearch.exe 启动检查失败，退出代码：$LASTEXITCODE"
        }
    }
    finally {
        Remove-Item Env:EXCELSEARCH_DATA_DIR -ErrorAction SilentlyContinue
        Remove-Item Env:EXCELSEARCH_SMOKE_TEST -ErrorAction SilentlyContinue
    }

    New-Item -ItemType Directory -Force $releaseDirectory | Out-Null
    if (Test-Path $portableArchive) {
        Remove-Item -Force $portableArchive
    }
    Compress-Archive -Path (Join-Path $projectRoot "dist\ExcelSearch\*") -DestinationPath $portableArchive

    $innoSetup = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $innoSetup) {
        & $innoSetup (Join-Path $projectRoot "packaging\windows\ExcelSearch.iss")
    }
    else {
        Write-Warning "未安装 Inno Setup 6，已生成便携版 ZIP，但没有生成安装包。"
        Write-Warning "安装 Inno Setup 6 后重新运行本脚本即可生成 ExcelSearch-Setup.exe。"
    }

    Write-Host ""
    Write-Host "Windows 成品位于：$releaseDirectory"
}
finally {
    Pop-Location
}
