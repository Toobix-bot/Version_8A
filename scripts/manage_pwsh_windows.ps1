<#
Interactive helper to list and manage open PowerShell/pwsh windows.

Usage:
  From repository root (C:\GPT\Version_8):
    .\scripts\manage_pwsh_windows.ps1

Features:
  - Lists running powershell/pwsh processes with PID, start time and command line
  - Highlights processes whose CommandLine contains the current repository folder name (Version_8)
  - Option to bring a chosen PID to foreground (visible window)
  - Option to stop chosen PIDs (with confirmation)

Note: Bringing to foreground requires the process to have a visible MainWindowHandle.
#>

Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoName = Split-Path $repoRoot -Leaf

function Get-PwshProcesses() {
    $rows = @()
    $candidates = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'powershell|pwsh' }
    foreach ($p in $candidates) {
        $cmd = $p.CommandLine
        $matchesRepo = $false
        if ($cmd -and $cmd -match [regex]::Escape($repoName)) { $matchesRepo = $true }
        $rows += [PSCustomObject]@{
            PID = $p.ProcessId
            Name = $p.Name
            CommandLine = $cmd
            MatchesRepo = $matchesRepo
            ExecutablePath = $p.ExecutablePath
        }
    }
    return $rows | Sort-Object -Property MatchesRepo -Descending, PID
}

function Show-List($list) {
    Write-Host "Detected PowerShell processes:" -ForegroundColor Cyan
    $i = 0
    $list | ForEach-Object {
        $i++
        $tag = if ($_.MatchesRepo) { '*' } else { ' ' }
        Write-Host ('[{0}] PID:{1,-6} {2} {3}' -f $i, $_.PID, $tag, ($_.CommandLine -replace '\s{2,}', ' '))
    }
}

function Bring-ToFront([int]$pid) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@
    try {
        $p = Get-Process -Id $pid -ErrorAction Stop
        if ($p.MainWindowHandle -ne 0) {
            [Win]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
            [Win]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
            Write-Host "Brought PID $pid to foreground." -ForegroundColor Green
        } else {
            Write-Warning "Process $pid has no visible window (MainWindowHandle=0)."
        }
    } catch {
        Write-Warning "Failed to bring PID $pid to front: $_"
    }
}

function Stop-PIDs([int[]]$pids) {
    foreach ($pid in $pids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "Stopped PID $pid" -ForegroundColor Yellow
        } catch {
            Write-Warning "Failed to stop PID $pid: $_"
        }
    }
}

# Main interactive loop
while ($true) {
    $list = Get-PwshProcesses
    if (-not $list) { Write-Host "No PowerShell/pwsh processes found."; break }
    Show-List $list

    Write-Host "\nOptions:"
    Write-Host "  f <n>   - bring item number n to foreground"
    Write-Host "  s <n,n> - stop item numbers (comma separated)"
    Write-Host "  q       - quit"
    $cmd = Read-Host "Enter command"
    if (-not $cmd) { continue }
    $parts = $cmd.Trim().Split(' ',2)
    $op = $parts[0].ToLower()
    $arg = if ($parts.Count -gt 1) { $parts[1].Trim() } else { '' }
    switch ($op) {
        'q' { break }
        'f' {
            if (-not $arg) { Write-Warning 'Missing argument for f'; continue }
            $idx = [int]$arg
            $item = $list[$idx - 1]
            if ($null -eq $item) { Write-Warning 'Invalid item'; continue }
            Bring-ToFront $item.PID
        }
        's' {
            if (-not $arg) { Write-Warning 'Missing argument for s'; continue }
            $sel = $arg -split ',' | ForEach-Object { [int]$_.Trim() }
            $pids = @()
            foreach ($n in $sel) {
                $itm = $list[$n - 1]
                if ($itm) { $pids += $itm.PID }
            }
            if (-not $pids) { Write-Warning 'No valid selections'; continue }
            Write-Host "About to stop PIDs: $($pids -join ', ')" -ForegroundColor Yellow
            $ok = Read-Host "Type YES to confirm"
            if ($ok -eq 'YES') { Stop-PIDs $pids } else { Write-Host 'Aborted' }
        }
        default { Write-Warning 'Unknown command' }
    }
}

Write-Host 'Done.' -ForegroundColor Cyan
