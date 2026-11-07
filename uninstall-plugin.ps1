[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& codex plugin remove 'aseprite-local@aseprite-local-market' --json
if ($LASTEXITCODE -ne 0) { throw 'Plugin removal failed' }
Write-Output 'Codex plugin removed. Source project, artwork and Aseprite menu extension are preserved. Remove the Codex Aseprite Bridge extension in Aseprite Preferences > Extensions if needed.'
