# Facet Studio local launcher (Windows PowerShell).
# Starts: Mongo (mongodb-memory-server) -> preview server -> LibreChat -> browser.
#
# Configure with environment variables (or edit the defaults below):
#   FACET_STUDIO_PROJECT_ROOT  project directory (default: parent of this script)
#   FACET_STUDIO_LIBRECHAT_ROOT  LibreChat clone (default: sibling "librechat")
#   FACET_STUDIO_PYTHON  Python executable (default: "python")
#
# After editing LibreChat client code: cd $LibreChat; npm run frontend; restart backend.

$Project = if ($env:FACET_STUDIO_PROJECT_ROOT) {
  $env:FACET_STUDIO_PROJECT_ROOT
} else {
  (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

$LibreChat = if ($env:FACET_STUDIO_LIBRECHAT_ROOT) {
  $env:FACET_STUDIO_LIBRECHAT_ROOT
} else {
  Join-Path (Split-Path $Project -Parent) 'librechat'
}

$Python = if ($env:FACET_STUDIO_PYTHON) {
  $env:FACET_STUDIO_PYTHON
} else {
  'python'
}

if (-not (Test-Path $LibreChat)) {
  throw "LibreChat not found at $LibreChat. Set FACET_STUDIO_LIBRECHAT_ROOT."
}

Write-Host "Project:   $Project"
Write-Host "LibreChat: $LibreChat"
Write-Host "Python:    $Python"

Write-Host "Starting Mongo..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$LibreChat'; node scripts/dev-mongo.cjs"

Start-Sleep -Seconds 3
Write-Host "Starting preview server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Project'; `$env:PYTHONPATH='src'; & '$Python' -m facet_studio.preview_server"

Start-Sleep -Seconds 2
Write-Host "Starting LibreChat..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$LibreChat'; npm run backend"

Start-Sleep -Seconds 8
Start-Process "http://localhost:3080"
Write-Host "Open http://localhost:3080 ; agent: Facet Studio ; preview: http://127.0.0.1:8765"
