$pids = @(5668,8460,25212,30980)
foreach ($p in $pids) {
  try {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$p"
    Write-Output ("PID $p CMD: $($proc.CommandLine)")
  } catch {
    Write-Output ("PID $p CMD: <err>")
  }
}
