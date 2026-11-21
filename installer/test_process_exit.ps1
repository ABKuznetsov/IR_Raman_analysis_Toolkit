$ErrorActionPreference = 'Stop'
foreach ($expected in @(0, 7)) {
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /c exit $expected" -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot/test-process-out.log" -RedirectStandardError "$PSScriptRoot/test-process-err.log" -PassThru
    $null = $process.Handle
    while (-not $process.HasExited) { Start-Sleep -Milliseconds 50 }
    $process.WaitForExit()
    $actual = $process.ExitCode
    if ($null -eq $actual -or $actual -ne $expected) { throw "Expected exit code $expected; received '$actual'" }
}
'Exit code checks passed'
