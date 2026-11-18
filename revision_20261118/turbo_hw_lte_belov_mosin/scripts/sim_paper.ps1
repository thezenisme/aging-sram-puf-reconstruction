param([string]$VivadoBin = '')
$ErrorActionPreference = 'Stop'
$env:PROCESSOR_ARCHITECTURE = 'AMD64'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not $VivadoBin) {
    if ($env:VIVADO_HOME) { $VivadoBin = Join-Path $env:VIVADO_HOME 'bin' }
    else { $VivadoBin = Split-Path -Parent (Get-Command xvhdl.bat -ErrorAction Stop).Source }
}
function Invoke-Checked([string]$program, [string[]]$arguments) {
    & $program @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$program failed with exit code $LASTEXITCODE" }
}
Invoke-Checked "$VivadoBin/xvhdl.bat" @('--2008', 'rtl/ram_replacements.vhd', 'rtl/bcjr_turbo_decoder.vhd', 'rtl/lte_interleaver.vhd', 'rtl/lte_turbo_decoder.vhd')
Invoke-Checked "$VivadoBin/xvlog.bat" @('-sv', 'rtl/turbo_lte_4096_2048_compare_top.sv')
$cases = @(
    @{ Name = 'random20261017'; Define = '' },
    @{ Name = 'random19'; Define = 'TB_VECTOR_SEED19' },
    @{ Name = 'all_zero'; Define = 'TB_VECTOR_ZEROS' },
    @{ Name = 'all_one'; Define = 'TB_VECTOR_ONES' }
)
foreach ($case in $cases) {
    $arguments = @('-sv')
    if ($case.Define) { $arguments += @('-d', $case.Define) }
    $arguments += 'tb/tb_turbo_compare.sv'
    Invoke-Checked "$VivadoBin/xvlog.bat" $arguments
    Invoke-Checked "$VivadoBin/xelab.bat" @('tb_turbo_compare', '-s', 'paper_turbo_sim', '-debug', 'typical')
    $output = & "$VivadoBin/xsim.bat" paper_turbo_sim -runall
    if ($LASTEXITCODE -ne 0 -or ($output | Select-String 'TURBO_COMPARE_MISMATCH|Fatal:')) {
        throw "Simulation failed: $($case.Name)"
    }
    if (-not ($output | Select-String '^TURBO_COMPARE_PASS cycles=258995 inputs=4096 outputs=2048$')) {
        throw "Missing complete payload check: $($case.Name)"
    }
    if (-not ($output | Select-String '^TURBO_LATENCY start_to_done=258993 clk')) {
        throw "START-to-DONE endpoint mismatch: $($case.Name)"
    }
    $output | Select-String '^TURBO_LATENCY|^TURBO_COMPARE_PASS' | ForEach-Object { $_.Line }
    Write-Output "PAPER_TURBO_PASS $($case.Name)"
}
