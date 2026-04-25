param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [ValidateSet("xsct", "linux")]
  [string]$ResetMethod = "xsct",
  [string]$XsctBat = "F:\Xilinx\Vitis\2020.2\bin\xsct.bat",
  [string]$BitstreamImage = "system_wrapper.bit",
  [string]$BitstreamSizeHex = "0x3DBB6A",
  [string]$DeviceTreeImage = "system_ir_boot.dtb",
  [int]$BootInterruptTimeoutSeconds = 45,
  [int]$OverallTimeoutSeconds = 180,
  [int]$PollMs = 100,
  [switch]$RunPostBootSelftest,
  [string]$RemoteDir = "/home/root/irdet_demo"
)

$ErrorActionPreference = "Stop"

$logDir = Join-Path $RepoRoot "build\ac880_uboot_pl_preload"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "uboot_ir_boot_$timestamp.log"

$port = New-Object System.IO.Ports.SerialPort $ComPort, $BaudRate, 'None', 8, 'one'
$port.ReadTimeout = 200
$port.WriteTimeout = 500
$port.NewLine = "`n"
$builder = New-Object System.Text.StringBuilder

function Add-Log {
  param([string]$Text)
  if ([string]::IsNullOrEmpty($Text)) {
    return
  }
  [void]$builder.Append($Text)
  Write-Host -NoNewline $Text
}

function Read-Chunk {
  param([System.IO.Ports.SerialPort]$SerialPort)
  try {
    return $SerialPort.ReadExisting()
  } catch {
    return ""
  }
}

function Wait-ForPattern {
  param(
    [System.IO.Ports.SerialPort]$SerialPort,
    [string]$Pattern,
    [int]$TimeoutSeconds,
    [ref]$AccumulatedText
  )

  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTime]::UtcNow -lt $deadline) {
    $chunk = Read-Chunk -SerialPort $SerialPort
    if ($chunk.Length -gt 0) {
      Add-Log -Text $chunk
      $AccumulatedText.Value += $chunk
      if ($AccumulatedText.Value -match $Pattern) {
        return $true
      }
    }
    Start-Sleep -Milliseconds $PollMs
  }
  return $false
}

function Invoke-XsctSystemReset {
  param(
    [string]$RepoPath,
    [string]$XsctPath
  )

  if (!(Test-Path $XsctPath)) {
    throw "XSCT not found: $XsctPath"
  }

  $resetTcl = Join-Path $RepoPath "build\ac880_uboot_pl_preload\xsct_reset_for_ir_boot.tcl"
  $tcl = @'
connect
targets -set -filter {name =~ "APU*"}
rst -system
exit
'@
  Set-Content -Path $resetTcl -Value $tcl -Encoding ASCII
  & $XsctPath $resetTcl | Out-Null
}

try {
  $port.Open()
  Start-Sleep -Milliseconds 300
  $port.DiscardInBuffer()
  $port.DiscardOutBuffer()
  $port.Write("`r`n")
  Start-Sleep -Milliseconds 300
  $null = Read-Chunk -SerialPort $port

  Add-Log -Text ("`r`n==== AC880 U-Boot IR boot test started at {0} ====`r`n" -f (Get-Date))
  if ($ResetMethod -eq "linux") {
    Add-Log -Text "[INFO] Triggering Linux reboot over serial...`r`n"
    $port.Write("reboot`n")
  } else {
    Add-Log -Text "[INFO] Triggering XSCT system reset...`r`n"
    Invoke-XsctSystemReset -RepoPath $RepoRoot -XsctPath $XsctBat
  }

  $allText = ""
  $seenAutoboot = Wait-ForPattern -SerialPort $port -Pattern "Hit any key to stop autoboot" -TimeoutSeconds $BootInterruptTimeoutSeconds -AccumulatedText ([ref]$allText)
  if (-not $seenAutoboot) {
    throw "Did not see U-Boot autoboot countdown within $BootInterruptTimeoutSeconds seconds."
  }

  Add-Log -Text "`r`n[INFO] Interrupting autoboot...`r`n"
  $port.Write(" ")

  $promptSeen = Wait-ForPattern -SerialPort $port -Pattern "(Zynq>|=>)" -TimeoutSeconds 10 -AccumulatedText ([ref]$allText)
  if (-not $promptSeen) {
    throw "Did not reach a U-Boot prompt after interrupting autoboot."
  }

  $commands = @(
    "setenv bitstream_image $BitstreamImage",
    "setenv bitstream_size $BitstreamSizeHex",
    "setenv devicetree_image $DeviceTreeImage",
    "run sdboot"
  )
  foreach ($command in $commands) {
    Add-Log -Text ("`r`n[INFO] U-Boot command: {0}`r`n" -f $command)
    $port.Write($command + "`n")
    Start-Sleep -Milliseconds 250
  }

  $deadline = [DateTime]::UtcNow.AddSeconds($OverallTimeoutSeconds)
  $linuxSeen = $false
  while ([DateTime]::UtcNow -lt $deadline) {
    $chunk = Read-Chunk -SerialPort $port
    if ($chunk.Length -gt 0) {
      Add-Log -Text $chunk
      $allText += $chunk
      if ($allText -match "Kernel panic - not syncing") {
        throw "Linux boot panicked after early bitstream load."
      }
      if ($allText -match "root@AC880_System:.*#") {
        $linuxSeen = $true
        break
      }
    }
    Start-Sleep -Milliseconds $PollMs
  }

  if (-not $linuxSeen) {
    throw "Linux prompt did not come back before timeout."
  }

  if ($RunPostBootSelftest) {
    Add-Log -Text "`r`n[INFO] Running post-boot PL selftest...`r`n"
    Start-Sleep -Seconds 3
    $drainDeadline = [DateTime]::UtcNow.AddSeconds(5)
    while ([DateTime]::UtcNow -lt $drainDeadline) {
      $chunk = Read-Chunk -SerialPort $port
      if ($chunk.Length -gt 0) {
        Add-Log -Text $chunk
        $allText += $chunk
      } else {
        Start-Sleep -Milliseconds $PollMs
      }
    }
    $port.Write("`r`n")
    Start-Sleep -Milliseconds 300
    $port.Write("dmesg -n 1 >/dev/null 2>&1 || true`n")
    Start-Sleep -Milliseconds 200
    $port.Write("cd $RemoteDir`n")
    Start-Sleep -Milliseconds 200
    $port.Write("./lib/ld-linux-armhf.so.3 --library-path ./lib ./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio`n")
    $selftestSeen = Wait-ForPattern -SerialPort $port -Pattern "(PL dw3x3 selftest rc=0|PL dw3x3 linux tool rc=0)" -TimeoutSeconds 40 -AccumulatedText ([ref]$allText)
    if (-not $selftestSeen) {
      throw "Post-boot PL selftest did not report success."
    }
  }

  Add-Log -Text "`r`n[PASS] AC880 U-Boot IR boot validation succeeded.`r`n"
} finally {
  Set-Content -Path $logPath -Value $builder.ToString() -Encoding ASCII
  Write-Host ""
  Write-Host "Saved log to $logPath"
  if ($port.IsOpen) {
    $port.Close()
  }
}
