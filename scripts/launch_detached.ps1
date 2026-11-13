# Launches a command detached from the calling console (WMI spawn, own process group) so it keeps
# running after an interactive session ends. Output goes to results/logs/<name>.out.
# Usage: powershell -File scripts/launch_detached.ps1 -Name queue -Command "python scripts/queue.py"
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [Parameter(Mandatory = $true)][string]$Command
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "results\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$out = Join-Path $logDir "$Name.out"
$cmdline = "cmd.exe /c `"cd /d `"$root`" && $Command >> `"$out`" 2>&1`""
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ CreateFlags = [uint32](0x08000000 -bor 0x200); ShowWindow = [uint16]0 }
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmdline; CurrentDirectory = $root; ProcessStartupInformation = $startup }
"launched '$Name' pid=$($r.ProcessId) log=$out"
$r.ProcessId | Out-File -Encoding ascii (Join-Path $logDir "$Name.pid")
