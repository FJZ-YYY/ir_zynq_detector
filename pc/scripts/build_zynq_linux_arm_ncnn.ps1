param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$NcnnBuildDir = "G:\FPGA\ir_zynq_detector\build\ncnn_arm_linux_min"
)

$ErrorActionPreference = "Stop"

$cmake = Join-Path $RepoRoot ".venv-train\Scripts\cmake.exe"
$ninja = Join-Path $RepoRoot ".venv-train\Scripts\ninja.exe"
$buildDir = Join-Path $RepoRoot "build\zynq_linux_arm_ncnn"
$toolchain = Join-Path $RepoRoot "zynq_linux\cmake\toolchains\vitis_aarch32_linux.cmake"
$ncnnLib = Join-Path $NcnnBuildDir "src\libncnn.a"
$detectorApp = Join-Path $buildDir "irdet_linux_ncnn_app"
$plToolApp = Join-Path $buildDir "irdet_linux_pl_dw3x3_tool"
$ncnnIncludes = @(
  (Join-Path $RepoRoot "tools\ncnn\src"),
  (Join-Path $NcnnBuildDir "src")
) -join ';'

if (!(Test-Path $cmake)) { throw "cmake not found: $cmake" }
if (!(Test-Path $ninja)) { throw "ninja not found: $ninja" }
if (!(Test-Path $toolchain)) { throw "toolchain file not found: $toolchain" }
if (!(Test-Path $ncnnLib)) { throw "ARM ncnn library not found: $ncnnLib" }

$env:PATH = "$(Split-Path $ninja);$env:PATH"

if (Test-Path $buildDir) {
  Remove-Item -Recurse -Force $buildDir
}

Write-Host "Configuring ARM Linux detector app..."
$cmakeArgs = @(
  "-S", (Join-Path $RepoRoot "zynq_linux"),
  "-B", $buildDir,
  "-G", "Ninja",
  "-DCMAKE_BUILD_TYPE=Release",
  "-DCMAKE_TOOLCHAIN_FILE=$toolchain",
  "-DIRDET_REPO_ROOT=$RepoRoot",
  "-DIRDET_NCNN_INCLUDE_DIRS=$ncnnIncludes",
  "-DIRDET_NCNN_LIBRARY=$ncnnLib"
)
& $cmake @cmakeArgs
if ($LASTEXITCODE -ne 0) {
  throw "ARM app configure failed with exit code $LASTEXITCODE"
}

Write-Host "Building ARM Linux detector app..."
& $cmake --build $buildDir -j 4
if ($LASTEXITCODE -ne 0) {
  throw "ARM app build failed with exit code $LASTEXITCODE"
}

foreach ($artifact in @($detectorApp, $plToolApp)) {
  if (!(Test-Path $artifact)) {
    throw "Expected ARM Linux artifact not found: $artifact"
  }
}

Get-Item $detectorApp, $plToolApp | Select-Object FullName,Length,LastWriteTime
