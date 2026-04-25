param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [string[]]$PreloadCommands = @(
    "fatload mmc 0:1 `${loadaddr} irdet_pl_preload.scr; source `${loadaddr}",
    "fatload mmc 1:1 `${loadaddr} irdet_pl_preload.scr; source `${loadaddr}",
    "ext4load mmc 0:1 `${loadaddr} /irdet_pl_preload.scr; source `${loadaddr}",
    "ext4load mmc 1:1 `${loadaddr} /irdet_pl_preload.scr; source `${loadaddr}"
  ),
  [int]$OverallTimeoutSeconds = 180,
  [int]$BootInterruptTimeoutSeconds = 45,
  [int]$PollMs = 100,
  [switch]$RunPostBootSelftest,
  [string]$RemoteDir = "/home/root/irdet_demo"
)

$ErrorActionPreference = "Stop"

$logDir = Join-Path $RepoRoot "build\ac880_uboot_pl_preload"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "uboot_preload_boot_$timestamp.log"

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

try {
  $port.Open()
  Start-Sleep -Milliseconds 300
  $port.DiscardInBuffer()
  $port.DiscardOutBuffer()
  $port.Write("`r`n")
  Start-Sleep -Milliseconds 300
  $null = Read-Chunk -SerialPort $port

  Add-Log -Text ("`r`n==== AC880 U-Boot preload test started at {0} ====`r`n" -f (Get-Date))
  $port.Write("reboot`n")

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

  $commandWorked = $false
  foreach ($command in $PreloadCommands) {
    Add-Log -Text ("`r`n[INFO] Trying preload command: {0}`r`n" -f $command)
    $port.Write($command + "`n")

    $matched = Wait-ForPattern -SerialPort $port -Pattern "(PL preload done source=|WARNING: PL preload bundle did not find the bitstream|Loaded bitstream from FAT|Loaded bitstream from EXT4|Unknown command|Bad Linux ARM zImage magic)" -TimeoutSeconds 30 -AccumulatedText ([ref]$allText)
    if ($matched -and $allText -match "PL preload done source=") {
      $commandWorked = $true
      break
    }

    if ($allText -match "Running existing bootcmd") {
      # The script ran but did not print explicit success; continue with this path.
      $commandWorked = $true
      break
    }

    if ($allText -match "(Zynq>|=>)") {
      continue
    }
  }

  if (-not $commandWorked) {
    throw "None of the preload commands reached a successful hand-off."
  }

  Add-Log -Text "`r`n[INFO] Waiting for Linux prompt...`r`n"
  $linuxSeen = Wait-ForPattern -SerialPort $port -Pattern "root@AC880_System:.*#" -TimeoutSeconds ($OverallTimeoutSeconds - $BootInterruptTimeoutSeconds) -AccumulatedText ([ref]$allText)
  if (-not $linuxSeen) {
    throw "Linux prompt did not come back before timeout."
  }

  if ($RunPostBootSelftest) {
    Add-Log -Text "`r`n[INFO] Running post-boot PL selftest...`r`n"
    $port.Write("dmesg -n 1 >/dev/null 2>&1 || true`n")
    Start-Sleep -Milliseconds 200
    $port.Write("cd $RemoteDir`n")
    Start-Sleep -Milliseconds 200
    $port.Write("./lib/ld-linux-armhf.so.3 --library-path ./lib ./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio`n")

    $selftestSeen = Wait-ForPattern -SerialPort $port -Pattern "PL dw3x3 selftest rc=0" -TimeoutSeconds 40 -AccumulatedText ([ref]$allText)
    if (-not $selftestSeen) {
      throw "Post-boot PL selftest did not report success."
    }
  }

  Add-Log -Text "`r`n[PASS] AC880 U-Boot preload validation succeeded.`r`n"
} finally {
  Set-Content -Path $logPath -Value $builder.ToString() -Encoding ASCII
  Write-Host ""
  Write-Host "Saved log to $logPath"
  if ($port.IsOpen) {
    $port.Close()
  }
}
