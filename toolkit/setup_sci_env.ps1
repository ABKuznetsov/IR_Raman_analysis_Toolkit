param([switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
$workerPath = Join-Path $PSScriptRoot 'setup_sci_env.bat'
if (-not (Test-Path -LiteralPath $workerPath)) { throw 'Setup worker is missing.' }
if ($ValidateOnly) { Write-Output 'Setup worker found'; exit 0 }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$logRoot = Join-Path $env:LOCALAPPDATA 'Sci\logs\ir_raman_analysis_toolkit'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$form = New-Object System.Windows.Forms.Form
$form.Text = 'IR/Raman Phase Finder - Sci setup'
$form.Size = New-Object System.Drawing.Size(780, 520)
$form.MinimumSize = $form.Size
$form.StartPosition = 'CenterScreen'
$title = New-Object System.Windows.Forms.Label
$title.Text = 'Preparing the shared Sci environment'
$title.SetBounds(20, 18, 720, 28)
$title.Font = New-Object System.Drawing.Font('Segoe UI', 12)
$status = New-Object System.Windows.Forms.Label
$status.SetBounds(20, 55, 720, 25)
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.SetBounds(20, 86, 720, 20)
$bar.Style = 'Marquee'
$details = New-Object System.Windows.Forms.TextBox
$details.SetBounds(20, 120, 720, 280)
$details.Multiline = $true
$details.ReadOnly = $true
$details.ScrollBars = 'Both'
$details.WordWrap = $false
$details.Font = New-Object System.Drawing.Font('Consolas', 9)
$details.Anchor = 'Top, Bottom, Left, Right'
$button = New-Object System.Windows.Forms.Button
$button.SetBounds(630, 420, 110, 32)
$button.Anchor = 'Bottom, Right'
$button.Text = 'Cancel'
$logs = New-Object System.Windows.Forms.Button
$logs.SetBounds(20, 420, 130, 32)
$logs.Anchor = 'Bottom, Left'
$logs.Text = 'Open logs'
$logs.Add_Click({ Start-Process explorer.exe -ArgumentList $logRoot })
$form.Controls.AddRange(@($title, $status, $bar, $details, $button, $logs))
$script:worker = $null
$script:result = 1
$script:running = $false
$script:attempt = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
function Start-Setup {
    $script:attempt++
    $script:outLog = Join-Path $logRoot ('setup-output-' + $script:attempt + '.log')
    $script:errLog = Join-Path $logRoot ('setup-errors-' + $script:attempt + '.log')
    $script:worker = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c ""' + $workerPath + '" --worker"') -WindowStyle Hidden -RedirectStandardOutput $script:outLog -RedirectStandardError $script:errLog -PassThru
    # Retain the native handle so Windows PowerShell preserves the exit code.
    $null = $script:worker.Handle
    $script:started = Get-Date
    $script:running = $true
    $status.Text = 'Checking Python and creating Sci if needed...'
    $bar.Style = 'Marquee'
    $button.Text = 'Cancel'
    $timer.Start()
}
$timer.Add_Tick({
    try {
        $output = if (Test-Path $script:outLog) { Get-Content $script:outLog -Raw } else { '' }
        $errors = if (Test-Path $script:errLog) { Get-Content $script:errLog -Raw } else { '' }
        $text = [string]$output + [Environment]::NewLine + [string]$errors
        if ($details.Text -ne $text) {
            $details.Text = $text
            $details.SelectionStart = $details.TextLength
            $details.ScrollToCaret()
        }
        $elapsed = [int]((Get-Date) - $script:started).TotalSeconds
        $stage = 'Checking Python / creating environment'
        if ($output -match 'Checking pip') { $stage = 'Checking build tools' }
        if ($output -match 'Installing IR/Raman') { $stage = 'Installing dependencies (first setup may take several minutes)' }
        $steps = [regex]::Matches([string]$output, '\[(\d+)/(\d+)\] Installing package: ([^\r\n]+)')
        if ($steps.Count) {
            $last = $steps[$steps.Count - 1]
            $stage = 'Package ' + $last.Groups[1].Value + '/' + $last.Groups[2].Value + ': ' + $last.Groups[3].Value
        }
        if ($output -match 'Testing installed scientific packages') { $stage = 'Testing the scientific environment' }
        if ($errors -match 'Retrying|SSLError|ConnectionResetError') { $stage = 'Network connection failed; pip is retrying. See details below' }
        $status.Text = "$stage - ${elapsed}s"
        if ($script:worker.HasExited) {
            $timer.Stop()
            $script:worker.WaitForExit()
            $script:result = $script:worker.ExitCode
            $script:running = $false
            $bar.Style = 'Continuous'
            if ($script:result -eq 0) {
                $bar.Value = 100
                $status.Text = 'Sci is ready. You can launch IR/Raman Phase Finder.'
                $button.Text = 'Close'
            } else {
                $bar.Value = 0
                $status.Text = "Setup failed (exit code $($script:result)). Check details or logs, then retry."
                $button.Text = 'Retry'
            }
        }
    } catch { $status.Text = $_.Exception.Message }
})
$button.Add_Click({
    if ($script:running) { $form.Close() }
    elseif ($script:result -eq 0) { $form.Close() }
    else { Start-Setup }
})
$form.Add_FormClosing({
    if ($script:running) {
        $answer = [System.Windows.Forms.MessageBox]::Show('Cancel environment setup?', 'Sci setup', 'YesNo', 'Question')
        if ($answer -ne 'Yes') { $_.Cancel = $true; return }
        & taskkill.exe /PID $script:worker.Id /T /F | Out-Null
        $script:result = 1
    }
    $timer.Stop()
})
$form.Add_Shown({ Start-Setup })
[void]$form.ShowDialog()
$timer.Dispose()
$form.Dispose()
exit $script:result
