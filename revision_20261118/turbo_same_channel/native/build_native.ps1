param([string]$Compiler = 'gcc')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$vendorDir = Join-Path $projectDir 'vendor\srslte_17_12'
$buildDir = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$flags = @('-std=c11', '-O3', '-Wall', '-Wextra', '-Wno-sign-compare',
           '-Wno-unused-parameter', '-Wno-unused-variable', '-fno-fast-math',
           '-I' + $vendorDir, '-I' + (Join-Path $PSScriptRoot 'shim'))
$sources = @((Join-Path $PSScriptRoot 'turbo_native.c'),
             (Join-Path $PSScriptRoot 'decoder_bridge.c'),
             (Join-Path $PSScriptRoot 'shim_support.c'),
             (Join-Path $vendorDir 'turbocoder.c'),
             (Join-Path $vendorDir 'tc_interl_lte.c'),
             (Join-Path $vendorDir 'rm_turbo.c'))
$dll = Join-Path $projectDir 'turbo_native.dll'
& $Compiler @flags '-shared' @sources '-o' $dll '-lm'
if ($LASTEXITCODE -ne 0) { throw 'DLL compilation failed.' }
$selftest = Join-Path $buildDir 'native_selftest.exe'
& $Compiler @flags @sources (Join-Path $PSScriptRoot 'native_selftest.c') '-o' $selftest '-lm'
if ($LASTEXITCODE -ne 0) { throw 'Self-test compilation failed.' }
& $selftest
if ($LASTEXITCODE -ne 0) { throw 'Native self-test failed.' }
Get-FileHash -LiteralPath $dll -Algorithm SHA256
