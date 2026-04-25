param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [string]$RemoteDir = "/home/root/irdet_demo",
  [string]$RemoteTmpArchive = "/tmp/irdet_real_layer_update.tar.gz",
  [switch]$RefreshBundle,
  [switch]$RunDemo
)

$ErrorActionPreference = "Stop"

$bundleDir = Join-Path $RepoRoot "build\zynq_linux_demo_bundle"
$archivePath = Join-Path $RepoRoot "build\ac880_real_layer_serial_update.tar.gz"
$packageScript = Join-Path $RepoRoot "pc\scripts\package_zynq_linux_demo.ps1"
$uploadScript = Join-Path $RepoRoot "pc\scripts\upload_file_over_serial.py"
$serialInvokeScript = Join-Path $RepoRoot "pc\scripts\invoke_ac880_serial_command.ps1"

foreach ($path in @($packageScript, $uploadScript, $serialInvokeScript)) {
  if (!(Test-Path $path)) {
    throw "Script not found: $path"
  }
}

if ($RefreshBundle -or !(Test-Path $bundleDir)) {
  Write-Host "Refreshing zynq_linux_demo_bundle..."
  & powershell -ExecutionPolicy Bypass -File $packageScript -RepoRoot $RepoRoot
  if ($LASTEXITCODE -ne 0) {
    throw "package_zynq_linux_demo.ps1 failed with exit code $LASTEXITCODE"
  }
}

if (!(Test-Path $bundleDir)) {
  throw "Bundle directory not found: $bundleDir"
}

Write-Host "Creating minimal real-layer serial update archive..."
$env:IRDET_BUNDLE_DIR = $bundleDir
$env:IRDET_ARCHIVE_PATH = $archivePath
@'
import os
import tarfile

bundle_dir = os.environ["IRDET_BUNDLE_DIR"]
archive_path = os.environ["IRDET_ARCHIVE_PATH"]
members = [
    "app/irdet_linux_ncnn_app",
    "run_demo_gray8_with_pl_real_layer.sh",
    "bundle_manifest.json",
    "README.txt",
]

pl_case_dir = os.path.join(bundle_dir, "data", "pl_real_layer_case")
if not os.path.isdir(pl_case_dir):
    raise SystemExit(f"Missing real-layer case directory: {pl_case_dir}")

for root, _, files in os.walk(pl_case_dir):
    for name in sorted(files):
        rel = os.path.relpath(os.path.join(root, name), bundle_dir)
        members.append(rel.replace("\\", "/"))

with tarfile.open(archive_path, "w:gz") as tar:
    for rel in members:
        local_path = os.path.join(bundle_dir, rel.replace("/", os.sep))
        if not os.path.exists(local_path):
            raise SystemExit(f"Missing bundle member: {local_path}")
        tar.add(local_path, arcname=rel)

print(f"SERIAL_UPDATE_ARCHIVE_OK {archive_path}")
'@ | python -
if ($LASTEXITCODE -ne 0) {
  throw "Failed to build serial update archive"
}

Get-Item $archivePath | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize

Write-Host "Uploading archive over serial to $RemoteTmpArchive ..."
& python $uploadScript `
  --port $ComPort `
  --baud $BaudRate `
  --local-file $archivePath `
  --remote-path $RemoteTmpArchive `
  --disable-echo
if ($LASTEXITCODE -ne 0) {
  throw "upload_file_over_serial.py failed with exit code $LASTEXITCODE"
}

$commands = @(
  "mkdir -p $RemoteDir/data/pl_real_layer_case",
  "tar -xzf $RemoteTmpArchive -C $RemoteDir",
  "chmod +x $RemoteDir/run_demo_gray8_with_pl_real_layer.sh $RemoteDir/app/irdet_linux_ncnn_app",
  "rm -f $RemoteTmpArchive",
  "ls -la $RemoteDir",
  "ls -la $RemoteDir/data/pl_real_layer_case"
)

if ($RunDemo) {
  $commands += @(
    "cd $RemoteDir",
    "./run_demo_gray8_with_pl_real_layer.sh"
  )
}

Write-Host "Extracting update archive on AC880 over serial..."
& powershell -ExecutionPolicy Bypass -File $serialInvokeScript `
  -ComPort $ComPort `
  -BaudRate $BaudRate `
  -Commands $commands `
  -InterCommandDelayMs 500 `
  -IdleThresholdMs 2000 `
  -MaxReadSeconds 45
if ($LASTEXITCODE -ne 0) {
  throw "invoke_ac880_serial_command.ps1 failed with exit code $LASTEXITCODE"
}
