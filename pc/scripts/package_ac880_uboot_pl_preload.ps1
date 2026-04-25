param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$script = Join-Path $RepoRoot "pc\scripts\package_ac880_uboot_pl_preload.py"

if (!(Test-Path $python)) { throw "Python not found: $python" }
if (!(Test-Path $script)) { throw "Script not found: $script" }

& $python $script --repo-root $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "package_ac880_uboot_pl_preload.py failed with exit code $LASTEXITCODE"
}
