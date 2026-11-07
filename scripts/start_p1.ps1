# Facet Studio P1/P2 local launcher (Windows PowerShell)
# Adjust $Project / $LibreChat / $Python if your paths differ.
# Starts: Mongo (mongodb-memory-server) -> preview server -> LibreChat -> browser.
# After editing LibreChat client code: cd $LibreChat; npm run frontend; then restart backend.

$Project  = "D:\秋招\个人作品\1023视频写作"
$LibreChat = "D:\luno_external\librechat"
$Python   = "D:\anaconda\envs\myagent\python.exe"

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
