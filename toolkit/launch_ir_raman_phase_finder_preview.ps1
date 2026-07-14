param(
    [string]$AppId = "ir_raman_phase_finder"
)

$ErrorActionPreference = "Stop"

function Resolve-AppRoot {
    if ($PSScriptRoot) { return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
    return (Get-Location).Path
}

function Ensure-Folder {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Compare-VersionText {
    param([string]$Left, [string]$Right)
    try {
        return ([version]$Left).CompareTo([version]$Right)
    } catch {
        return [string]::Compare($Left, $Right, $true)
    }
}

function New-Label {
    param(
        [string]$Text,
        [int]$X,
        [int]$Y,
        [int]$W,
        [int]$H,
        [float]$Size = 9,
        [string]$Style = "Regular",
        [System.Drawing.Color]$Color = [System.Drawing.Color]::FromArgb(31, 41, 55)
    )
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point -ArgumentList $X, $Y
    $label.Size = New-Object System.Drawing.Size -ArgumentList $W, $H
    $label.Font = New-Object System.Drawing.Font -ArgumentList "Segoe UI", $Size, ([System.Drawing.FontStyle]::$Style)
    $label.ForeColor = $Color
    $label.BackColor = [System.Drawing.Color]::Transparent
    return $label
}

function New-StateBitmap {
    param([string]$State)
    $bmp = New-Object System.Drawing.Bitmap 34, 34
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)
    if ($State -eq "OK") {
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(46, 125, 50)), 2.6
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(232, 245, 233))
        $g.FillEllipse($brush, 4, 4, 26, 26)
        $g.DrawEllipse($pen, 4, 4, 26, 26)
        $g.DrawLines($pen, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 11, 18), (New-Object System.Drawing.Point 15, 22), (New-Object System.Drawing.Point 23, 13)))
    } elseif ($State -eq "Error") {
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(185, 28, 28)), 2.6
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(254, 226, 226))
        $g.FillEllipse($brush, 4, 4, 26, 26)
        $g.DrawEllipse($pen, 4, 4, 26, 26)
        $g.DrawLine($pen, 12, 12, 22, 22)
        $g.DrawLine($pen, 22, 12, 12, 22)
    } elseif ($State -eq "Working") {
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(37, 99, 235)), 2.8
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(239, 246, 255))
        $g.FillEllipse($brush, 4, 4, 26, 26)
        $g.DrawArc($pen, 7, 7, 20, 20, 25, 285)
        $g.FillEllipse((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(37, 99, 235))), 15, 15, 4, 4)
    } else {
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(148, 163, 184)), 2.2
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(248, 250, 252))
        $g.FillEllipse($brush, 4, 4, 26, 26)
        $g.DrawEllipse($pen, 4, 4, 26, 26)
    }
    $g.Dispose()
    return $bmp
}

function Set-StateIcon {
    param([int]$Index, [string]$State)
    if ($script:StepIconBoxes.Count -le $Index) { return }
    $box = $script:StepIconBoxes[$Index]
    if ($box.Image) { $box.Image.Dispose() }
    $box.Image = New-StateBitmap $State
}

function Pause-PreviewStep {
    Start-Sleep -Milliseconds 2000
}

function Add-StepRow {
    param([int]$Index, [string]$Title, [string]$Detail, [int]$Y)
    $iconBox = New-Object System.Windows.Forms.PictureBox
    $iconBox.Location = New-Object System.Drawing.Point -ArgumentList 430, ($Y + 8)
    $iconBox.Size = New-Object System.Drawing.Size -ArgumentList 34, 34
    $iconBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::CenterImage
    $iconBox.Image = New-StateBitmap "Waiting"
    $script:Form.Controls.Add($iconBox)
    $script:StepIconBoxes.Add($iconBox)

    $titleLabel = New-Label $Title 492 ($Y - 2) 315 25 11 "Bold" ([System.Drawing.Color]::FromArgb(15, 23, 42))
    $script:Form.Controls.Add($titleLabel)
    $detailLabel = New-Label $Detail 492 ($Y + 24) 315 40 9.5 "Regular" ([System.Drawing.Color]::FromArgb(75, 85, 99))
    $script:Form.Controls.Add($detailLabel)
    $statusLabel = New-Label "Waiting" 784 ($Y + 11) 102 22 9.5 "Regular" ([System.Drawing.Color]::FromArgb(37, 99, 235))
    $statusLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $script:Form.Controls.Add($statusLabel)
    $divider = New-Object System.Windows.Forms.Panel
    $divider.Location = New-Object System.Drawing.Point -ArgumentList 430, ($Y + 62)
    $divider.Size = New-Object System.Drawing.Size -ArgumentList 456, 1
    $divider.BackColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
    $script:Form.Controls.Add($divider)
    $script:StepStatusLabels.Add($statusLabel)
    $script:StepDetailLabels.Add($detailLabel)
}

function Set-Step {
    param([int]$Index, [string]$Status, [string]$Detail, [string]$Tone = "Blue")
    if ($Status -match "OK") { Set-StateIcon $Index "OK" } elseif ($Tone -eq "Red" -or $Status -match "Failed") { Set-StateIcon $Index "Error" } elseif ($Status -match "Checking|Installing|Loading|Starting|Opening") { Set-StateIcon $Index "Working" } else { Set-StateIcon $Index "Waiting" }
    if ($script:StepStatusLabels.Count -gt $Index) {
        $label = $script:StepStatusLabels[$Index]
        $label.Text = $Status
        if ($Tone -eq "Green") { $label.ForeColor = [System.Drawing.Color]::FromArgb(46, 125, 50) }
        elseif ($Tone -eq "Red") { $label.ForeColor = [System.Drawing.Color]::FromArgb(185, 28, 28) }
        elseif ($Tone -eq "Muted") { $label.ForeColor = [System.Drawing.Color]::FromArgb(100, 116, 139) }
        else { $label.ForeColor = [System.Drawing.Color]::FromArgb(37, 99, 235) }
    }
    if ($script:StepDetailLabels.Count -gt $Index -and $Detail) {
        $script:StepDetailLabels[$Index].Text = $Detail
    }
    [System.Windows.Forms.Application]::DoEvents()
}

function Set-ProgressText {
    param([int]$Value, [string]$Text)
    [System.Windows.Forms.Application]::DoEvents()
}

function Get-SetupProgressMessage {
    param([string]$LogPath)
    if (-not (Test-Path -LiteralPath $LogPath)) { return "Starting environment setup" }
    try { $lines = Get-Content -LiteralPath $LogPath -Tail 40 -ErrorAction Stop } catch { return "Preparing environment" }
    $joined = ($lines -join "`n")
    if ($joined -match "Downloading Python") { return "Downloading Python 3.11" }
    if ($joined -match "Installing Python") { return "Installing Python 3.11" }
    if ($joined -match "Creating venv") { return "Creating shared Python environment" }
    if ($joined -match "Upgrading pip") { return "Upgrading pip" }
    if ($joined -match "Failed to install package:\s*([^`r`n]+)") { return "Failed to install package: " + $Matches[1].Trim() }
    if ($joined -match "Installing package:\s*([^`r`n]+)") {
        $packageName = $Matches[1].Trim()
        if ($packageName -match "^(PySide6|scipy|numpy|pandas|pyqtgraph)$") { return "Installing package: $packageName (this can take several minutes)" }
        return "Installing package: $packageName"
    }
    if ($joined -match "Installing IR/Raman Phase Finder requirements") { return "Installing IR/Raman requirements" }
    if ($joined -match "Collecting ") { return "Downloading Python packages" }
    if ($joined -match "Installing collected packages") { return "Installing Python packages" }
    if ($joined -match "Successfully installed") { return "Finalizing installed packages" }
    if ($joined -match "setup complete") { return "Environment setup complete" }
    if ($joined -match "setup failed") { return "Environment setup failed" }
    for ($idx = $lines.Count - 1; $idx -ge 0; $idx--) {
        $line = ([string]$lines[$idx]).Trim()
        if ($line -and $line.Length -lt 120) { return $line }
    }
    return "Preparing environment"
}

function Wait-SetupProcessWithProgress {
    param([System.Diagnostics.Process]$Process, [string]$LogPath)
    $lastMessage = ""
    $tick = 0
    while (-not $Process.HasExited) {
        $message = Get-SetupProgressMessage $LogPath
        if ($message -ne $lastMessage -or ($tick % 6) -eq 0) {
            $dots = "." * (($tick % 4) + 1)
            Set-Step 1 "Installing$dots" $message "Blue"
            Set-ProgressText 28 $message
            $lastMessage = $message
        }
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 500
        $tick++
    }
    $Process.Refresh()
    $message = Get-SetupProgressMessage $LogPath
    if ($message) {
        Set-Step 1 "Checking..." $message "Blue"
        Set-ProgressText 28 $message
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Get-StartupLogTail {
    param([string]$LogPath)
    if (-not $LogPath -or -not (Test-Path -LiteralPath $LogPath)) { return "" }
    try {
        $tail = Get-Content -LiteralPath $LogPath -Tail 18 -ErrorAction Stop
        $text = ($tail -join "`r`n").Trim()
        if ($text.Length -gt 1600) { return $text.Substring($text.Length - 1600) }
        return $text
    } catch { return "" }
}

function Wait-ApplicationMainWindow {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 120,
        [string]$LogPath = "",
        [string]$ReadyFile = ""
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $tick = 0
    while ((Get-Date) -lt $deadline) {
        if ($ReadyFile -and (Test-Path -LiteralPath $ReadyFile)) { return $true }
        if ($Process.HasExited) {
            if ($Process.ExitCode -eq 0) { return $true }
            $details = Get-StartupLogTail $LogPath
            if ($details) {
                throw "IR/Raman Phase Finder closed during startup. Exit code: $($Process.ExitCode)`r`n`r`nStartup log:`r`n$details`r`n`r`nFull log: $LogPath"
            }
            throw "IR/Raman Phase Finder closed during startup. Exit code: $($Process.ExitCode)`r`nFull log: $LogPath"
        }
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero -or (Test-ProcessHasVisibleWindow $Process.Id)) { return $true }
        $dots = "." * (($tick % 4) + 1)
        Set-Step 4 "Starting$dots" "Waiting for the main application window" "Blue"
        Set-ProgressText 96 "Starting IR/Raman Phase Finder$dots"
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.Application]::DoEvents()
        $tick++
    }
    $details = Get-StartupLogTail $LogPath
    if ($details) {
        throw "IR/Raman Phase Finder is running, but the main window did not appear within $TimeoutSeconds seconds.`r`n`r`nStartup log:`r`n$details`r`n`r`nFull log: $LogPath"
    }
    throw "IR/Raman Phase Finder is running, but the main window did not appear within $TimeoutSeconds seconds.`r`nFull log: $LogPath"
}

function Show-OwnedQuestion {
    param([string]$Message, [string]$Title)
    $script:Form.TopMost = $true
    $script:Form.Activate()
    [System.Windows.Forms.Application]::DoEvents()
    $result = [System.Windows.Forms.MessageBox]::Show($script:Form, $Message, $Title, [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Information)
    $script:Form.TopMost = $false
    return $result
}

function Invoke-UpdateDownload {
    param(
        [string]$Url,
        [string]$OutFile
    )
    if (-not $Url) { throw "Update installer URL is not available." }
    $errors = New-Object System.Collections.Generic.List[string]
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
    }

    try {
        Write-LauncherLog "Downloading update with Invoke-WebRequest: $Url"
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 900 -MaximumRedirection 10 -Headers @{ "User-Agent" = "IR-Raman-Phase-Finder-Updater" }
        if ((Test-Path -LiteralPath $OutFile) -and ((Get-Item -LiteralPath $OutFile).Length -gt 1024)) { return }
        $errors.Add("Invoke-WebRequest produced an empty or incomplete file.") | Out-Null
    } catch {
        $errors.Add("Invoke-WebRequest: " + $_.Exception.Message) | Out-Null
    }

    try {
        Write-LauncherLog "Downloading update with BITS: $Url"
        Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
        Start-BitsTransfer -Source $Url -Destination $OutFile -DisplayName "IR/Raman Phase Finder update" -Description "Downloading IR/Raman Phase Finder update" -ErrorAction Stop
        if ((Test-Path -LiteralPath $OutFile) -and ((Get-Item -LiteralPath $OutFile).Length -gt 1024)) { return }
        $errors.Add("BITS produced an empty or incomplete file.") | Out-Null
    } catch {
        $errors.Add("BITS: " + $_.Exception.Message) | Out-Null
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        try {
            Write-LauncherLog "Downloading update with curl.exe: $Url"
            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            $downloadFolder = [System.IO.Path]::GetDirectoryName($OutFile)
            $curlOutLog = Join-Path $downloadFolder "curl_update.out.log"
            $curlErrLog = Join-Path $downloadFolder "curl_update.err.log"
            $curlProcess = Start-Process -FilePath $curl.Source -ArgumentList @("-L", "--fail", "--retry", "3", "--connect-timeout", "45", "--max-time", "900", "-A", "IR-Raman-Phase-Finder-Updater", "-o", $OutFile, $Url) -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $curlOutLog -RedirectStandardError $curlErrLog
            if ($curlProcess.ExitCode -eq 0 -and (Test-Path -LiteralPath $OutFile) -and ((Get-Item -LiteralPath $OutFile).Length -gt 1024)) { return }
            $errors.Add("curl.exe exit code: " + $curlProcess.ExitCode) | Out-Null
            if (Test-Path -LiteralPath $curlErrLog) {
                $curlErrorText = (Get-Content -LiteralPath $curlErrLog -Raw -ErrorAction SilentlyContinue)
                if ($curlErrorText) {
                    $errors.Add("curl.exe details: " + $curlErrorText.Trim()) | Out-Null
                }
            }
        } catch {
            $errors.Add("curl.exe: " + $_.Exception.Message) | Out-Null
        }
    } else {
        $errors.Add("curl.exe is not available.") | Out-Null
    }

    throw "Could not download the update installer automatically.`r`n" + ($errors -join "`r`n")
}

function Download-And-RunUpdate {
    param([string]$Url, [string]$ExpectedSha256, [string]$LatestVersion)
    if (-not $Url) { throw "Update installer URL is not available." }
    Set-Step 3 "Downloading" "The update installer can take a few minutes on a slow connection." "Blue"
    [System.Windows.Forms.Application]::DoEvents()
    Ensure-Folder $updateRoot
    $fileName = [System.IO.Path]::GetFileName(([System.Uri]$Url).AbsolutePath)
    if (-not $fileName) { $fileName = "IR_Raman_analysis_Toolkit_Setup_$LatestVersion.exe" }
    $targetPath = Join-Path $updateRoot $fileName
    Set-Step 3 "Downloading" ("Downloading update " + $LatestVersion) "Blue"
    [System.Windows.Forms.Application]::DoEvents()
    Invoke-UpdateDownload $Url $targetPath
    if ($ExpectedSha256) {
        Set-Step 3 "Checking" "Verifying downloaded installer" "Blue"
        [System.Windows.Forms.Application]::DoEvents()
        $actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetPath).Hash.ToLowerInvariant()
        if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
            Remove-Item -LiteralPath $targetPath -Force -ErrorAction SilentlyContinue
            throw "Downloaded installer checksum does not match the update manifest."
        }
    }
    Set-Step 3 "Ready" "Starting update installer" "Green"
    [System.Windows.Forms.Application]::DoEvents()
    Start-Process -FilePath $targetPath | Out-Null
}

function Stop-PreparedAppProcess {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        try {
            Write-LauncherLog "Stopping prepared Python app before update installer starts. PID=$($Process.Id)"
            $Process.Kill()
        } catch {
        }
    }
}

$appRoot = Resolve-AppRoot
$sciRoot = Join-Path $env:LOCALAPPDATA "Sci"
$envRoot = Join-Path $sciRoot "env"
$appDataRoot = Join-Path $sciRoot "apps\ir_raman_analysis_toolkit"
$dataRoot = Join-Path $appDataRoot "data"
$cacheRoot = Join-Path $dataRoot "cache"
$matplotlibRoot = Join-Path $appDataRoot "matplotlib"
$settingsRoot = Join-Path $appDataRoot "settings"
$logsRoot = Join-Path $sciRoot "logs\ir_raman_analysis_toolkit"
$updateRoot = Join-Path $sciRoot "updates"
$launcherLog = Join-Path $logsRoot "launcher_preview.log"
function Write-LauncherLog {
    param([string]$Message)
    try {
        if (-not (Test-Path -LiteralPath $logsRoot)) { New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null }
        "[$(Get-Date -Format s)] $Message" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
    } catch {
    }
}
Write-LauncherLog "Preview launcher started from $appRoot"
$pythonExe = Join-Path $envRoot "Scripts\python.exe"
$setupBat = Join-Path $appRoot "toolkit\setup_sci_env.bat"
$manifestPath = Join-Path $appRoot "toolkit\manifest.json"
$appManifestPath = Join-Path $appRoot "Vibrational_Finder\app.json"
$appPackageRoot = Join-Path $appRoot "Vibrational_Finder"
$appIconPath = Join-Path $appRoot "icon.png"
$localVersion = "0.0.0"
$entryModule = "vibrational_finder.apps.finder_gui"
$releaseUrl = ""
$manifestUrl = ""
$updateManifestUrl = ""
$installerUrl = ""
$installerSha256 = ""

if (Test-Path -LiteralPath $appManifestPath) {
    try {
        $appManifest = Get-Content -LiteralPath $appManifestPath -Raw | ConvertFrom-Json
        if ($appManifest.version) { $localVersion = [string]$appManifest.version }
        if ($appManifest.entry_module) { $entryModule = [string]$appManifest.entry_module }
    } catch {}
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class IrRamanWindowFinder {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);
}
"@

function Test-ProcessHasVisibleWindow {
    param([int]$ProcessId)
    $callback = [IrRamanWindowFinder+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        [uint32]$windowProcessId = 0
        [void][IrRamanWindowFinder]::GetWindowThreadProcessId($hWnd, [ref]$windowProcessId)
        if ($windowProcessId -eq [uint32]$ProcessId -and [IrRamanWindowFinder]::IsWindowVisible($hWnd) -and [IrRamanWindowFinder]::GetWindowTextLength($hWnd) -gt 0) {
            $script:IrRamanVisibleWindowFound = $true
            return $false
        }
        return $true
    }
    $script:IrRamanVisibleWindowFound = $false
    [void][IrRamanWindowFinder]::EnumWindows($callback, [IntPtr]::Zero)
    $found = [bool]$script:IrRamanVisibleWindowFound
    Remove-Variable -Name IrRamanVisibleWindowFound -Scope Script -ErrorAction SilentlyContinue
    return $found
}

$script:Form = New-Object System.Windows.Forms.Form
$script:Form.Text = "IR/Raman Phase Finder"
$script:Form.StartPosition = "CenterScreen"
$script:Form.Size = New-Object System.Drawing.Size -ArgumentList 940, 590
$script:Form.MinimumSize = New-Object System.Drawing.Size -ArgumentList 940, 590
$script:Form.FormBorderStyle = "FixedSingle"
$script:Form.MaximizeBox = $false
$script:Form.BackColor = [System.Drawing.Color]::FromArgb(248, 250, 252)

$leftPanel = New-Object System.Windows.Forms.Panel
$leftPanel.Location = New-Object System.Drawing.Point -ArgumentList 0, 0
$leftPanel.Size = New-Object System.Drawing.Size -ArgumentList 400, 552
$leftPanel.BackColor = [System.Drawing.Color]::White
$script:Form.Controls.Add($leftPanel)

$splitter = New-Object System.Windows.Forms.Panel
$splitter.Location = New-Object System.Drawing.Point -ArgumentList 400, 0
$splitter.Size = New-Object System.Drawing.Size -ArgumentList 1, 552
$splitter.BackColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
$script:Form.Controls.Add($splitter)

if (Test-Path -LiteralPath $appIconPath) {
    $picture = New-Object System.Windows.Forms.PictureBox
    $picture.Location = New-Object System.Drawing.Point -ArgumentList 60, 92
    $picture.Size = New-Object System.Drawing.Size -ArgumentList 280, 280
    $picture.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $picture.Image = [System.Drawing.Image]::FromFile($appIconPath)
    $leftPanel.Controls.Add($picture)
}

$brand = New-Label "IR/Raman Phase Finder" 42 390 336 46 21 "Bold" ([System.Drawing.Color]::FromArgb(15, 23, 42))
$leftPanel.Controls.Add($brand)
$subtitle = New-Label "Phase identification from`r`nIR and Raman spectra" 60 438 290 58 12 "Regular" ([System.Drawing.Color]::FromArgb(71, 85, 105))
$leftPanel.Controls.Add($subtitle)
$versionLabel = New-Label "Version $localVersion" 60 512 180 24 9 "Regular" ([System.Drawing.Color]::FromArgb(100, 116, 139))
$leftPanel.Controls.Add($versionLabel)

$title = New-Label "Starting IR/Raman Phase Finder..." 430 46 430 42 19 "Bold" ([System.Drawing.Color]::FromArgb(15, 23, 42))
$script:Form.Controls.Add($title)
$topHint = New-Label "Preparing runtime, sources, updates and user settings." 432 82 420 24 9.5 "Regular" ([System.Drawing.Color]::FromArgb(100, 116, 139))
$script:Form.Controls.Add($topHint)

$script:StepStatusLabels = New-Object System.Collections.Generic.List[System.Windows.Forms.Label]
$script:StepDetailLabels = New-Object System.Collections.Generic.List[System.Windows.Forms.Label]
$script:StepIconBoxes = New-Object System.Collections.Generic.List[System.Windows.Forms.PictureBox]
Add-StepRow 0 "Checking application folders" "User data directory`r`nCache directory" 132
Add-StepRow 1 "Checking runtime" "Sci Python environment`r`nScientific packages" 204
Add-StepRow 2 "Checking spectral sources" "RRUFF, OpenSpecy and user libraries" 276
Add-StepRow 3 "Checking for updates" ("Current version: " + $localVersion) 348
Add-StepRow 4 "Loading settings" "Opening the main application window" 420
$script:Form.Show()
[System.Windows.Forms.Application]::DoEvents()

try {
    Set-Step 0 "Checking..." "Creating user data and cache folders" "Blue"
    Ensure-Folder $sciRoot
    Ensure-Folder $appDataRoot
    Ensure-Folder $dataRoot
    Ensure-Folder $logsRoot
    Ensure-Folder $cacheRoot
    Ensure-Folder $matplotlibRoot
    Ensure-Folder $settingsRoot
    Ensure-Folder $updateRoot
    Set-Step 0 "OK" "User data and cache folders are ready" "Green"

    Start-Sleep -Milliseconds 650
    Set-Step 1 "Checking..." "Looking for Sci runtime" "Blue"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        if (-not (Test-Path -LiteralPath $setupBat)) { throw "Setup script was not found: $setupBat" }
        $setupLog = Join-Path $logsRoot "setup.log"
        $setupProcess = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "`"$setupBat`"") -PassThru -WindowStyle Hidden
        Wait-SetupProcessWithProgress $setupProcess $setupLog
        if ($setupProcess.ExitCode -ne 0) {
            throw "Environment setup failed: $(Get-SetupProgressMessage $setupLog). See log: $setupLog"
        }
    }
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Python executable was not found: $pythonExe" }
    Set-Step 1 "OK" "Using Sci runtime" "Green"

    Write-LauncherLog "Preparing Python app in the background while preview steps continue."
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:IR_RAMAN_DATA_DIR = $dataRoot
    $env:IR_RAMAN_PHASE_FINDER_CACHE_DIR = $cacheRoot
    $env:MPLCONFIGDIR = $matplotlibRoot
    $env:QT_OPENGL = "software"
    $env:QT_QUICK_BACKEND = "software"
    $env:QT_ANGLE_PLATFORM = "warp"
    $env:QT_QPA_PLATFORM = "windows"
    if ($env:PYTHONPATH) { $env:PYTHONPATH = "$appPackageRoot;$env:PYTHONPATH" } else { $env:PYTHONPATH = $appPackageRoot }
    $startupLog = Join-Path $logsRoot "ir_raman_phase_finder_startup.log"
    $readyFile = Join-Path $logsRoot "ir_raman_phase_finder_ready.flag"
    $preparedFile = Join-Path $logsRoot "ir_raman_phase_finder_prepared.flag"
    $showSignalFile = Join-Path $logsRoot "ir_raman_phase_finder_show.signal"
    Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $preparedFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $showSignalFile -Force -ErrorAction SilentlyContinue
    Write-LauncherLog "Starting Python app with $pythonExe -m $entryModule"
    "[$(Get-Date -Format s)] Starting IR/Raman Phase Finder from $appRoot" | Set-Content -LiteralPath $startupLog -Encoding UTF8
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $pythonExe
    $startInfo.Arguments = "-m $entryModule"
    $startInfo.WorkingDirectory = $appRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
    $startInfo.EnvironmentVariables["IR_RAMAN_DATA_DIR"] = $dataRoot
    $startInfo.EnvironmentVariables["IR_RAMAN_PHASE_FINDER_CACHE_DIR"] = $cacheRoot
    $startInfo.EnvironmentVariables["MPLCONFIGDIR"] = $matplotlibRoot
    $startInfo.EnvironmentVariables["IR_RAMAN_PHASE_FINDER_PREPARED_FILE"] = $preparedFile
    $startInfo.EnvironmentVariables["IR_RAMAN_PHASE_FINDER_SHOW_SIGNAL_FILE"] = $showSignalFile
    $startInfo.EnvironmentVariables["IR_RAMAN_PHASE_FINDER_READY_FILE"] = $readyFile
    $startInfo.EnvironmentVariables["PYTHONPATH"] = $env:PYTHONPATH
    $startInfo.EnvironmentVariables["QT_OPENGL"] = "software"
    $startInfo.EnvironmentVariables["QT_QUICK_BACKEND"] = "software"
    $startInfo.EnvironmentVariables["QT_ANGLE_PLATFORM"] = "warp"
    $startInfo.EnvironmentVariables["QT_QPA_PLATFORM"] = "windows"
    $appProcess = New-Object System.Diagnostics.Process
    $appProcess.StartInfo = $startInfo
    Register-ObjectEvent -InputObject $appProcess -EventName OutputDataReceived -Action { if ($EventArgs.Data) { Add-Content -LiteralPath $Event.MessageData -Value $EventArgs.Data } } -MessageData $startupLog | Out-Null
    Register-ObjectEvent -InputObject $appProcess -EventName ErrorDataReceived -Action { if ($EventArgs.Data) { Add-Content -LiteralPath $Event.MessageData -Value $EventArgs.Data } } -MessageData $startupLog | Out-Null
    $null = $appProcess.Start()
    Write-LauncherLog "Python app process started. PID=$($appProcess.Id)"
    $appProcess.BeginOutputReadLine()
    $appProcess.BeginErrorReadLine()

    Pause-PreviewStep
    Set-Step 2 "Checking..." "Preparing local source cache folders" "Blue"
    Ensure-Folder (Join-Path $cacheRoot "rruff")
    Ensure-Folder (Join-Path $cacheRoot "openspecy")
    Set-Step 2 "OK" "Spectral source cache is ready" "Green"

    Pause-PreviewStep
    Set-Step 3 "Checking..." ("Current version: " + $localVersion) "Blue"
    if (Test-Path -LiteralPath $manifestPath) {
        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $appInfo = $manifest.apps.$AppId
            if ($appInfo.release_url) { $releaseUrl = [string]$appInfo.release_url }
            if ($appInfo.manifest_url) { $manifestUrl = [string]$appInfo.manifest_url }
            if ($appInfo.update_manifest_url) { $updateManifestUrl = [string]$appInfo.update_manifest_url }
            if ($appInfo.installer_url) { $installerUrl = [string]$appInfo.installer_url }
            if ($appInfo.installer_sha256) { $installerSha256 = [string]$appInfo.installer_sha256 }
        } catch {}
    }
    $updateStatus = [ordered]@{
        checked_at = (Get-Date).ToString("s")
        app_id = $AppId
        current_version = $localVersion
        latest_version = $localVersion
        update_available = $false
        release_url = $releaseUrl
        installer_url = $installerUrl
        installer_sha256 = $installerSha256
        error = $null
    }
    if ($manifestUrl -or $updateManifestUrl) {
        try {
            $remoteUrl = $manifestUrl
            if ($updateManifestUrl) { $remoteUrl = $updateManifestUrl }
            $remote = Invoke-RestMethod -Uri $remoteUrl -UseBasicParsing -TimeoutSec 5
            if ($remote -is [string]) { $remote = $remote | ConvertFrom-Json }
            $remoteApp = $remote
            if ($remote.apps -and $remote.apps.$AppId) { $remoteApp = $remote.apps.$AppId }
            if ($remoteApp.version) {
                $latestVersion = [string]$remoteApp.version
                $updateStatus.latest_version = $latestVersion
                if ((Compare-VersionText $latestVersion $localVersion) -gt 0) {
                    $updateStatus.update_available = $true
                    if ($remoteApp.release_url) { $updateStatus.release_url = [string]$remoteApp.release_url }
                    if ($remoteApp.installer_url) { $updateStatus.installer_url = [string]$remoteApp.installer_url }
                    if ($remoteApp.installer_sha256) { $updateStatus.installer_sha256 = [string]$remoteApp.installer_sha256 }
                    if ($remoteApp.assets -and $remoteApp.assets.Count -gt 0) {
                        $asset = $remoteApp.assets | Select-Object -First 1
                        if ($asset.url) { $updateStatus.installer_url = [string]$asset.url }
                        if ($asset.sha256) { $updateStatus.installer_sha256 = [string]$asset.sha256 }
                    }
                    Set-Step 3 "Update" ("$localVersion -> $latestVersion") "Blue"
                    $summaryLines = New-Object System.Collections.Generic.List[string]
                    if ($remoteApp.summary) {
                        foreach ($line in $remoteApp.summary) {
                            $textLine = [string]$line
                            if ($textLine.Trim()) { $summaryLines.Add("- " + $textLine.Trim()) | Out-Null }
                        }
                    }
                    if ($summaryLines.Count -eq 0) {
                        $summaryLines.Add("- See the release notes for details.") | Out-Null
                    }
                    $message = "A new IR/Raman Phase Finder version is available: $latestVersion.`r`nCurrent version: $localVersion`r`n`r`nWhat changed:`r`n" + ($summaryLines -join "`r`n") + "`r`n`r`nDownload and start the installer now?"
                    $choice = Show-OwnedQuestion $message "IR/Raman Phase Finder update available"
                    if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {
                        $downloadTarget = $updateStatus.installer_url
                        if (-not $downloadTarget) { $downloadTarget = $updateStatus.release_url }
                        try {
                            Download-And-RunUpdate $downloadTarget $updateStatus.installer_sha256 $latestVersion
                            ($updateStatus | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath (Join-Path $updateRoot "$AppId.json") -Encoding UTF8
                            Stop-PreparedAppProcess $appProcess
                            $script:Form.Close()
                            return
                        } catch {
                            $fallbackMessage = "The automatic update download failed:`r`n" + $_.Exception.Message + "`r`n`r`nOpen the release page instead?"
                            $fallbackChoice = Show-OwnedQuestion $fallbackMessage "IR/Raman Phase Finder update"
                            if ($fallbackChoice -eq [System.Windows.Forms.DialogResult]::Yes -and $updateStatus.release_url) {
                                Start-Process $updateStatus.release_url | Out-Null
                                Stop-PreparedAppProcess $appProcess
                                $script:Form.Close()
                                return
                            }
                        }
                    }
                } else {
                    Set-Step 3 "OK" ("No update available. Current version: $localVersion") "Green"
                }
            } else {
                Set-Step 3 "OK" ("No update available. Current version: $localVersion") "Green"
            }
        } catch {
            $updateStatus.error = $_.Exception.Message
            Set-Step 3 "Offline" "Update check unavailable" "Muted"
        }
    } else {
        Set-Step 3 "OK" "No update source configured" "Muted"
    }
    ($updateStatus | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath (Join-Path $updateRoot "$AppId.json") -Encoding UTF8

    Pause-PreviewStep
    Set-Step 4 "Opening..." "Showing the main application window" "Blue"
    "show" | Set-Content -LiteralPath $showSignalFile -Encoding UTF8
    Wait-ApplicationMainWindow $appProcess 120 $startupLog $readyFile | Out-Null
    Write-LauncherLog "Main application window is ready."
    Set-Step 4 "OK" "IR/Raman Phase Finder window is ready" "Green"
    Start-Sleep -Milliseconds 450
} catch {
    Write-LauncherLog ("Startup failed: " + $_.Exception.Message)
    Set-Step 4 "Failed" $_.Exception.Message "Red"
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "IR/Raman Phase Finder startup failed", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
} finally {
    if ($picture -and $picture.Image) { $picture.Image.Dispose() }
    $script:Form.Close()
    $script:Form.Dispose()
}
