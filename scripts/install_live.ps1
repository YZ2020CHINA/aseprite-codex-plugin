[CmdletBinding()]
param([string]$Destination = (Join-Path $PSScriptRoot '../.state/external/aseprite-live'))
$ErrorActionPreference = 'Stop'
$commit = '841fc81b519bd9d10f8ff9b29e43ea28e0c408f4'
if (Test-Path -LiteralPath $Destination) { throw 'Destination exists; choose a new directory or reuse the existing installation.' }
Write-Output 'Installing optional N7z/aseprite-live, independently licensed AGPL-3.0. See its LICENSE and source in the destination.'
& git clone https://github.com/N7z/aseprite-live.git $Destination
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
& git -C $Destination checkout --detach $commit
if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed' }
$cfgPath = Join-Path $PSScriptRoot '../config.json'
$cfg = Get-Content -Raw -LiteralPath $cfgPath | ConvertFrom-Json
$cfg | Add-Member -NotePropertyName aseprite_live_path -NotePropertyValue ([IO.Path]::GetFullPath($Destination)) -Force
[IO.File]::WriteAllText([IO.Path]::GetFullPath($cfgPath), ($cfg | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
Write-Output 'Ready. Call aseprite_viewer start from Codex. No upstream source is copied into the MIT plugin.'
