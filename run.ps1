<#
.SYNOPSIS
    Điều khiển dự án flow-reverse: khởi động / dừng / khởi động lại.

.DESCRIPTION
    Quản lý 2 tiến trình:
      - CloakBrowser  (CDP  port, mặc định 4022)  qua src/BrowserHost/launch_profile.py
      - Flow Bench WebUI (HTTP port, mặc định 4000) qua src/WebUI/app.py

    Trạng thái (PID) được ghi vào out/run/ để có thể dừng chính xác.

.EXAMPLE
    .\run.ps1 start                # khởi động browser + web (tự build lại UI nếu cần)
    .\run.ps1 start -NoBrowser     # chỉ khởi động web (browser đã mở sẵn)
    .\run.ps1 start -SkipBuild     # khởi động mà không build lại UI
    .\run.ps1 stop                 # dừng cả hai
    .\run.ps1 restart              # dừng rồi khởi động lại
    .\run.ps1 status               # xem trạng thái

.NOTES
    Yêu cầu: Python 3.11+ (dùng .venv nếu có) và npm (để build UI).

    Server phục vụ bundle tĩnh trong web/dist, đọc thẳng từ đĩa mỗi request. Vì vậy
    start/restart tự chạy `npm run build` khi web/dist không khớp mã nguồn web/ — nếu
    không, sửa UI sẽ không bao giờ hiện ra (web/dist giữ nguyên bản build cũ).
    Sửa backend Python thì vẫn phải `restart` (uvicorn không tự reload).
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
    [switch]$Open,        # mở UI trong trình duyệt mặc định sau khi start
    [switch]$SkipBuild    # không build lại UI (dùng bundle đang có trong web/dist)
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

# Vân tay của mã nguồn UI: băm nội dung mọi file có thể làm thay đổi bundle.
# Băm nội dung (không dùng mtime) vì checkout/pull có thể đặt lại mtime, khiến
# "dist mới hơn src" trong khi nội dung đã đổi — đó chính là kiểu làm cũ bị lừa.
function Get-WebSourceFingerprint {
    param([string]$WebDir)

    $sources = @(
        (Join-Path $WebDir "src"),
        (Join-Path $WebDir "index.html"),
        (Join-Path $WebDir "package.json"),
        (Join-Path $WebDir "package-lock.json"),
        (Join-Path $WebDir "vite.config.ts"),
        (Join-Path $WebDir "tsconfig.json")
    )

    $entries = New-Object System.Collections.Generic.List[string]
    foreach ($source in $sources) {
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $item = Get-Item -LiteralPath $source
        if ($item.PSIsContainer) {
            $files = Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction SilentlyContinue
        } else {
            $files = @($item)
        }
        foreach ($f in $files) {
            $rel = $f.FullName.Substring($WebDir.Length).TrimStart('\', '/')
            $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
            $entries.Add("$rel|$hash")
        }
    }

    $sorted = $entries | Sort-Object
    $payload = [System.Text.Encoding]::UTF8.GetBytes(($sorted -join "`n"))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($sha.ComputeHash($payload)).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
}

# Build lại UI khi web/dist không khớp mã nguồn web/ hiện tại.
# Trả về $true nếu web/dist/index.html tồn tại sau khi build (server phục vụ được UI).
function Sync-WebBuild {
    $webDir = Join-Path $Root "web"
    $distIndex = Join-Path $webDir "dist\index.html"
    # Stamp nằm trong dist nên tự vô hiệu khi thư mục bị xóa hoặc vite dọn outDir.
    $stampFile = Join-Path $webDir "dist\.build-stamp"

    if ($SkipBuild) {
        Write-Host "[skip] -SkipBuild: không build lại UI." -ForegroundColor DarkGray
        return (Test-Path $distIndex)
    }

    $fingerprint = Get-WebSourceFingerprint $webDir
    if ((Test-Path $distIndex) -and (Test-Path $stampFile)) {
        $built = (Get-Content -LiteralPath $stampFile -Raw -ErrorAction SilentlyContinue)
        if ($built -and $built.Trim() -eq $fingerprint) {
            Write-Host "[skip] web/dist đã khớp mã nguồn UI." -ForegroundColor DarkGray
            return $true
        }
        Write-Host "[build] Mã nguồn UI khác bản đã build — build lại..." -ForegroundColor Cyan
    } elseif (Test-Path $distIndex) {
        Write-Host "[build] web/dist không rõ nguồn gốc (thiếu .build-stamp) — build lại..." -ForegroundColor Cyan
    } else {
        Write-Host "[build] Chưa có web/dist — build UI..." -ForegroundColor Cyan
    }

    if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
        Write-Warning "Chưa có web/node_modules. Chạy trước:  cd web; npm ci"
        return $false
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Warning "Không tìm thấy npm trong PATH — không build được UI."
        return $false
    }

    Push-Location $webDir
    $code = 1
    try {
        # Qua cmd để stderr của npm/vite không thành NativeCommandError khi ErrorActionPreference=Stop
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        cmd.exe /c "npm run build 2>&1"
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
    } finally {
        Pop-Location
    }

    if ($code -ne 0) {
        if (Test-Path $distIndex) {
            Write-Warning "npm run build thất bại (exit code $code). Giữ bundle cũ trong web/dist — UI sẽ KHÔNG phải bản mới."
            return $true
        }
        Write-Warning "npm run build thất bại (exit code $code) và chưa có web/dist. Sửa lỗi build rồi chạy lại."
        return $false
    }

    if (Test-Path $distIndex) {
        $fingerprint | Out-File -LiteralPath $stampFile -Encoding ascii -NoNewline
        Write-Host "[ok] Đã build UI vào web/dist." -ForegroundColor Green
        return $true
    }
    Write-Warning "npm run build báo thành công nhưng không thấy web/dist/index.html."
    return $false
}

function Test-Cdp {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$CdpPort/json/version" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

function Test-Web {
    # /api/status dò CDP với timeout 2.5s ⇒ khi browser không chạy endpoint này mất ~3s
    # mới trả lời. Timeout phải lớn hơn thế, nếu không server khoẻ vẫn bị coi là chưa lên.
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/api/status" -UseBasicParsing -TimeoutSec 8 | Out-Null
        return $true
    } catch { return $false }
}

# Tìm PID đang lắng nghe một cổng (dự phòng khi không có pid file hoặc pid file bị cũ)
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
            if ([int]::TryParse($raw.Trim(), [ref]$parsed) -and $parsed -gt 0) { return $parsed }
        }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
function Start-Browser {
    if ($NoBrowser) { Write-Host "[skip] -NoBrowser: bỏ qua CloakBrowser." -ForegroundColor DarkGray; return }
    if (Test-Cdp) {
        Ensure-RunDir
        $portPid = Get-PortPid -Port $CdpPort
        if ($portPid) { $portPid | Out-File -Encoding ascii $BrowserPidFile }
        Write-Host "[skip] Browser CDP đã sẵn sàng tại cổng $CdpPort." -ForegroundColor DarkYellow
        return
    }

    Ensure-RunDir
    Write-Host "[start] Khởi động CloakBrowser (profile=$Profile, CDP=$CdpPort)..." -ForegroundColor Cyan
    & $Python (Join-Path $Root "src\BrowserHost\launch_profile.py") `
        --profile $Profile --port $CdpPort --wait --pid-file $BrowserPidFile
    if ($LASTEXITCODE -ne 0) { throw "Khởi động browser thất bại (exit code $LASTEXITCODE)." }
    
    $portPid = Get-PortPid -Port $CdpPort
    if ($portPid) { $portPid | Out-File -Encoding ascii $BrowserPidFile }
    Write-Host "[ok] Browser PID: $(Read-PidFile $BrowserPidFile)" -ForegroundColor Green
}

function Start-Web {
    # Build TRƯỚC khi kiểm tra cổng: server đang chạy vẫn phục vụ web/dist mới từ đĩa,
    # nên bỏ qua bước này khi server đã lên sẽ khiến UI kẹt ở bundle cũ.
    $hasDist = Sync-WebBuild
    if (-not $hasDist) {
        Write-Warning "web/dist/index.html chưa tồn tại — UI sẽ chỉ trả JSON. Chạy trước:  cd web; npm ci; npm run build"
    }

    if (Test-Web) {
        Ensure-RunDir
        $portPid = Get-PortPid -Port $WebPort
        if ($portPid) { $portPid | Out-File -Encoding ascii $WebPidFile }
        Write-Host "[skip] WebUI đã chạy tại cổng $WebPort." -ForegroundColor DarkYellow
        return
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
        $portPid = Get-PortPid -Port $WebPort
        if ($portPid) { $portPid | Out-File -Encoding ascii $WebPidFile }
        Write-Host "[ok] WebUI sẵn sàng: http://127.0.0.1:$WebPort  (PID $(Read-PidFile $WebPidFile))" -ForegroundColor Green
    } else {
        Write-Warning "WebUI chưa phản hồi sau 30s. Xem log: $WebLog  và  $WebErrLog"
    }
}

# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------
function Stop-TargetProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [int]$Port,
        [string[]]$AllowedProcessNames
    )

    $pidsToKill = [System.Collections.Generic.HashSet[int]]::new()

    # 1. Tìm PID đang lắng nghe trên cổng (nguồn chính xác nhất)
    $portPid = Get-PortPid -Port $Port
    if ($portPid) {
        $pidsToKill.Add($portPid) | Out-Null
    }

    # 2. Đọc PID từ file (dự phòng)
    $filePid = Read-PidFile $PidFile
    if ($filePid) {
        $proc = Get-Process -Id $filePid -ErrorAction SilentlyContinue
        if ($proc) {
            # Chỉ dừng nếu tên tiến trình hợp lệ, tránh đụng vào Windows Service khi PID bị tái sử dụng
            $procName = $proc.ProcessName.ToLower()
            $match = $false
            foreach ($allowed in $AllowedProcessNames) {
                if ($procName -like "*$($allowed.ToLower())*") {
                    $match = $true
                    break
                }
            }
            if ($match) {
                $pidsToKill.Add($filePid) | Out-Null
            } else {
                Write-Host "[warn] PID $filePid trong $(Split-Path $PidFile -Leaf) là '$($proc.ProcessName)' (không phải $Name). Bỏ qua PID này." -ForegroundColor DarkYellow
            }
        }
    }

    try {
        if ($pidsToKill.Count -gt 0) {
            foreach ($pidToKill in $pidsToKill) {
                Write-Host "[stop ] Dừng $Name (PID $pidToKill)..." -ForegroundColor Cyan
                # Dùng cmd /c để taskkill không ném NativeCommandError vào PowerShell khi ErrorActionPreference=Stop
                cmd.exe /c "taskkill /PID $pidToKill /T /F >nul 2>&1"
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }

            # Chờ giải phóng port tối đa 3s
            for ($i = 0; $i -lt 6; $i++) {
                if (-not (Get-PortPid -Port $Port)) { break }
                Start-Sleep -Milliseconds 500
            }

            Write-Host "[ok] Đã dừng $Name." -ForegroundColor Green
        } else {
            Write-Host "[skip] $Name không đang chạy." -ForegroundColor DarkGray
        }
    } finally {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Stop-Web {
    Stop-TargetProcess -Name "WebUI" -PidFile $WebPidFile -Port $WebPort -AllowedProcessNames @("python", "pythonw")
}

function Stop-Browser {
    if ($NoBrowser) { Write-Host "[skip] -NoBrowser: bỏ qua đóng browser." -ForegroundColor DarkGray; return }
    Stop-TargetProcess -Name "CloakBrowser" -PidFile $BrowserPidFile -Port $CdpPort -AllowedProcessNames @("chrome", "msedge", "brave", "chromium", "python", "pythonw")
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
