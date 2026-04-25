param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector"
)

$ErrorActionPreference = "Stop"

$cmake = Join-Path $RepoRoot ".venv-train\Scripts\cmake.exe"
$ninja = Join-Path $RepoRoot ".venv-train\Scripts\ninja.exe"
$buildDir = Join-Path $RepoRoot "build\ncnn_arm_linux_min"
$toolchain = Join-Path $RepoRoot "zynq_linux\cmake\toolchains\vitis_aarch32_linux.cmake"

function Remove-TreeSafe {
  param(
    [Parameter(Mandatory = $true)][string]$PathToRemove
  )

  if (!(Test-Path $PathToRemove)) {
    return
  }

  try {
    Remove-Item -Recurse -Force -LiteralPath $PathToRemove -ErrorAction Stop
  } catch {
    Start-Sleep -Milliseconds 500
    if (Test-Path $PathToRemove) {
      cmd /c rmdir /s /q "$PathToRemove" 2>$null | Out-Null
    }
  }
}

if (!(Test-Path $cmake)) { throw "cmake not found: $cmake" }
if (!(Test-Path $ninja)) { throw "ninja not found: $ninja" }
if (!(Test-Path $toolchain)) { throw "toolchain file not found: $toolchain" }

$env:PATH = "$(Split-Path $ninja);$env:PATH"

if (Test-Path $buildDir) {
  Remove-TreeSafe -PathToRemove $buildDir
}

Write-Host "Configuring ARM Linux ncnn build..."
$cmakeArgs = @(
  "-S", (Join-Path $RepoRoot "tools\ncnn"),
  "-B", $buildDir,
  "-G", "Ninja",
  "-DCMAKE_BUILD_TYPE=Release",
  "-DCMAKE_TOOLCHAIN_FILE=$toolchain",
  "-DNCNN_BUILD_TOOLS=OFF",
  "-DNCNN_BUILD_EXAMPLES=OFF",
  "-DNCNN_BUILD_BENCHMARK=OFF",
  "-DNCNN_BUILD_TESTS=OFF",
  "-DNCNN_PYTHON=OFF",
  "-DNCNN_VULKAN=OFF",
  "-DNCNN_OPENMP=OFF",
  "-DNCNN_THREADS=ON",
  "-DNCNN_SIMPLEOCV=OFF",
  "-DNCNN_SYSTEM_GLSLANG=OFF",
  "-DNCNN_PIXEL=OFF",
  "-DNCNN_PIXEL_ROTATE=OFF",
  "-DNCNN_PIXEL_AFFINE=OFF",
  "-DNCNN_PIXEL_DRAWING=OFF",
  "-DNCNN_GNU_INLINE_ASM=OFF",
  "-DNCNN_VFPV4=OFF",
  "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"
)
& $cmake @cmakeArgs
if ($LASTEXITCODE -ne 0) {
  throw "ncnn ARM configure failed with exit code $LASTEXITCODE"
}

Write-Host "Building ARM Linux ncnn..."
& $cmake --build $buildDir -j 4
if ($LASTEXITCODE -ne 0) {
  throw "ncnn ARM build failed with exit code $LASTEXITCODE"
}

Get-Item (Join-Path $buildDir "src\libncnn.a") | Select-Object FullName,Length,LastWriteTime
