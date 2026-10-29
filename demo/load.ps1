$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $here "..\reports"
New-Item -ItemType Directory -Force -Path (Join-Path $target "research"), (Join-Path $target "campaigns") | Out-Null
Copy-Item -Recurse -Force (Join-Path $here "data\research\*") (Join-Path $target "research")
Copy-Item -Recurse -Force (Join-Path $here "data\campaigns\*") (Join-Path $target "campaigns")
Write-Output "Demo data copied to $target"
