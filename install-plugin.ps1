[CmdletBinding()]
param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }),
    [string]$PythonPath,
    [string]$AsepritePath,
    [switch]$SkipAsepriteExtension
)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $bundled -PathType Leaf) { $PythonPath = $bundled }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python not found: $PythonPath" }
& $PythonPath -c 'import sys; assert sys.version_info >= (3,12), "Aseprite + aseprite-live requires Python 3.12+"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required' }
if (-not $AsepritePath) {
    $candidates = @('D:\Aseprite\Aseprite.exe', (Join-Path $env:ProgramFiles 'Aseprite\Aseprite.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Aseprite\Aseprite.exe'))
    $AsepritePath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $AsepritePath -or -not (Test-Path -LiteralPath $AsepritePath -PathType Leaf)) { throw 'Aseprite not found. Pass -AsepritePath with the full path to Aseprite.exe.' }
$codexExe = (Get-Command codex -ErrorAction Stop).Source
$configFile = Join-Path $PSScriptRoot 'config.json'
$cfgSource = if (Test-Path -LiteralPath $configFile) { $configFile } else { Join-Path $PSScriptRoot 'config.example.json' }
$cfg = Get-Content -Raw -LiteralPath $cfgSource | ConvertFrom-Json
$cfg.aseprite_path = [System.IO.Path]::GetFullPath($AsepritePath)
$json = $cfg | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($configFile, $json, [System.Text.UTF8Encoding]::new($false))
$priorCodexHome = $env:CODEX_HOME
$priorUtf8 = $env:PYTHONUTF8
try {
    New-Item -ItemType Directory -Path $CodexHome -Force | Out-Null
    $env:CODEX_HOME = $CodexHome
    $env:PYTHONUTF8 = '1'
    $icon = Join-Path (Split-Path -Parent $AsepritePath) 'data\icons\ase256.png'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw "Aseprite's bundled icon not found: $icon" }
    New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'assets') -Force | Out-Null
    Copy-Item -LiteralPath $icon -Destination (Join-Path $PSScriptRoot 'assets\aseprite.png') -Force
    & $PythonPath -X utf8 (Join-Path $PSScriptRoot 'scripts/build_plugin.py') --python $PythonPath
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    & $codexExe plugin marketplace add $PSScriptRoot --json
    if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed' }
    & $codexExe plugin add 'aseprite-local@aseprite-local-market' --json
    if ($LASTEXITCODE -ne 0) { throw 'Plugin install failed' }
    if (-not $SkipAsepriteExtension) {
        $extensionDir = Join-Path $env:APPDATA 'Aseprite/extensions'
        & $PythonPath -X utf8 (Join-Path $PSScriptRoot 'scripts/install_extension.py') --destination $extensionDir
        if ($LASTEXITCODE -ne 0) { throw 'Aseprite menu extension install failed' }
    }
    $listing = & $codexExe plugin list --marketplace aseprite-local-market --json
    if ($LASTEXITCODE -ne 0) { throw 'Plugin verification failed' }
    $listing
    Write-Output 'Installed. Start a new Codex chat to load the tools and skill. Restart Aseprite for the Connect to Codex menu command.'
} finally {
    $env:CODEX_HOME = $priorCodexHome
    $env:PYTHONUTF8 = $priorUtf8
}
