<#
.SYNOPSIS
    Điều khiển dự án flow-reverse: khởi động / dừng / khởi động lại.

.DESCRIPTION
    Quản lý 2 tiến trình:
      - CloakBrowser  (CDP  port, mặc định 4022)  qua src/BrowserHost/launch_profile.py
      - Flow Bench WebUI (HTTP port, mặc định 4000) qua src/WebUI/app.py

    Trạng thái (PID) được ghi vào out/run/ để có thể dừng chính xác.

.EXAMPLE
    .\run.ps1 start                # khởi động browser + web
    .\run.ps1 start -NoBrowser     # chỉ khởi động web (browser đã mở sẵn)
    .\run.ps1 stop                 # dừng cả hai
    .\run.ps1 restart              # dừng rồi khởi động lại
    .\run.ps1 status               # xem trạng thái

.NOTES
    Yêu cầu: Python 3.11+ (dùng .venv nếu có), web/dist đã build (npm run build).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Mode = "start",

    [string]$Profile = "flow_main",
    [int]$CdpPort = 4022,
    [int]$WebPort = 4000,

    [switch]$NoBrowser,   # bỏ qua phần browser, chỉ lo WebUI
    [switch]$Open         # mở UI trong trình duyệt mặc định sau khi start
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RunDir = Join-Path $Root "out\run"
$BrowserPidFile = Join-Path $RunDir "browser.pid"
$WebPidFile     = Join-Path $RunDir "web.pid"
$WebLog         = Join-Path $RunDir "web.log"
$WebErrLog      = Join-Path $RunDir "web.err.log"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Resolve-Python {
    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venv) { return $venv }
    return "python"
}
$Python = Resolve-Python

function Ensure-RunDir {
    if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir -Force | Out-Null }
}

function Test-Cdp {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$CdpPort/json/version" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

function Test-Web {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/api/status" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

# Tìm PID đang lắng nghe một cổng (dự phòng khi không có pid file)
function Get-PortPid {
    param([int]$Port)
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Read-PidFile {
    param([string]$File)
    if (Test-Path $File) {
        $raw = (Get-Content $File -Raw -ErrorAction SilentlyContinue)
        if ($raw) {
            $parsed = 0
            if ([int]::TryParse($raw.Trim(), [ref]$parsed)) { return $parsed }
        }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
function Start-Browser {
    if ($NoBrowser) { Write-Host "[skip] -NoBrowser: bỏ qua CloakBrowser." -ForegroundColor DarkGray; return }
    if (Test-Cdp)   { Write-Host "[skip] Browser CDP đã sẵn sàng tại cổng $CdpPort." -ForegroundColor DarkYellow; return }

    Ensure-RunDir
    Write-Host "[start] Khởi động CloakBrowser (profile=$Profile, CDP=$CdpPort)..." -ForegroundColor Cyan
    & $Python (Join-Path $Root "src\BrowserHost\launch_profile.py") `
        --profile $Profile --port $CdpPort --wait --pid-file $BrowserPidFile
    if ($LASTEXITCODE -ne 0) { throw "Khởi động browser thất bại (exit code $LASTEXITCODE)." }
    Write-Host "[ok] Browser PID: $(Read-PidFile $BrowserPidFile)" -ForegroundColor Green
}

function Start-Web {
    if (Test-Web) { Write-Host "[skip] WebUI đã chạy tại cổng $WebPort." -ForegroundColor DarkYellow; return }

    $dist = Join-Path $Root "web\dist\index.html"
    if (-not (Test-Path $dist)) {
        Write-Warning "web/dist/index.html chưa tồn tại. Chạy trước:  cd web; npm ci; npm run build"
    }

    Ensure-RunDir
    $webArgs = @("-m", "src.WebUI.app", "--port", "$WebPort", "--cdp-url", "http://127.0.0.1:$CdpPort")
    if ($Open) { $webArgs += "--open" }

    Write-Host "[start] Khởi động Flow Bench WebUI (port=$WebPort)..." -ForegroundColor Cyan
    $p = Start-Process -FilePath $Python -ArgumentList $webArgs `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $WebLog `
        -RedirectStandardError $WebErrLog `
        -PassThru -WindowStyle Hidden
    $p.Id | Out-File -Encoding ascii $WebPidFile

    Write-Host "[wait ] Đợi WebUI phản hồi (tối đa 30s)..." -ForegroundColor DarkGray
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Web) { $ok = $true; break }
    }
    if ($ok) {
        Write-Host "[ok] WebUI sẵn sàng: http://127.0.0.1:$WebPort  (PID $($p.Id))" -ForegroundColor Green
    } else {
        Write-Warning "WebUI chưa phản hồi sau 30s. Xem log: $WebLog  và  $WebErrLog"
    }
}

# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------
function Stop-Web {
    $procId = Read-PidFile $WebPidFile
    if (-not $procId) { $procId = Get-PortPid -Port $WebPort }

    if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
        Write-Host "[stop ] Dừng WebUI (PID $procId)..." -ForegroundColor Cyan
        taskkill /PID $procId /T /F 2>$null | Out-Null
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "[ok] Đã dừng WebUI." -ForegroundColor Green
    } else {
        Write-Host "[skip] WebUI không đang chạy." -ForegroundColor DarkGray
    }
    Remove-Item $WebPidFile -ErrorAction SilentlyContinue
}

function Stop-Browser {
    if ($NoBrowser) { Write-Host "[skip] -NoBrowser: bỏ qua đóng browser." -ForegroundColor DarkGray; return }

    $procId = Read-PidFile $BrowserPidFile
    if (-not $procId) { $procId = Get-PortPid -Port $CdpPort }

    if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
        Write-Host "[stop ] Đóng CloakBrowser (PID $procId)..." -ForegroundColor Cyan
        taskkill /PID $procId /T /F 2>$null | Out-Null
        Write-Host "[ok] Đã đóng browser." -ForegroundColor Green
    } else {
        Write-Host "[skip] Browser không đang chạy." -ForegroundColor DarkGray
    }
    Remove-Item $BrowserPidFile -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
function Show-Status {
    $cdp = Test-Cdp
    $web = Test-Web
    $cdpMark = if ($cdp) { "READY" } else { "OFF  " }
    $webMark = if ($web) { "READY" } else { "OFF  " }
    $cdpColor = if ($cdp) { "Green" } else { "Red" }
    $webColor = if ($web) { "Green" } else { "Red" }

    Write-Host "flow-reverse status"
    Write-Host -NoNewline "  CDP   : "; Write-Host $cdpMark -ForegroundColor $cdpColor -NoNewline
    Write-Host "  http://127.0.0.1:$CdpPort  (profile=$Profile)"
    Write-Host -NoNewline "  WebUI : "; Write-Host $webMark -ForegroundColor $webColor -NoNewline
    Write-Host "  http://127.0.0.1:$WebPort"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
switch ($Mode) {
    "start" {
        Start-Browser
        Start-Web
        Show-Status
    }
    "stop" {
        Stop-Web
        Stop-Browser
    }
    "restart" {
        Stop-Web
        Stop-Browser
        Start-Sleep -Seconds 1
        Start-Browser
        Start-Web
        Show-Status
    }
    "status" {
        Show-Status
    }
}
