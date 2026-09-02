[CmdletBinding()]
param(
    [ValidateSet('Square', 'SquarePua', 'Pua4', 'All')]
    [string]$Catalog = 'Square',
    [switch]$Spawn,
    [switch]$NoPager
)

$ErrorActionPreference = 'Stop'

if ($Spawn) {
    if ($Catalog -eq 'Pua4') {
        $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
        $config = Join-Path $root 'config\wezterm\pua4.lua'
        $arguments = @('--config-file', $config, 'start', '--cwd', $root, '--',
                       'powershell.exe', '-NoExit', '-ExecutionPolicy', 'Bypass',
                       '-File', $PSCommandPath, '-Catalog', $Catalog)
        if ($NoPager) { $arguments += '-NoPager' }
        Start-Process wezterm.exe -ArgumentList $arguments
    } else {
        $arguments = @('-p', 'Square Braille Shell', 'powershell.exe', '-NoExit',
                       '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
                       '-Catalog', $Catalog)
        if ($NoPager) { $arguments += '-NoPager' }
        Start-Process wt.exe -ArgumentList $arguments
    }
    return
}

function Get-Pua4Codepoint([int]$Mask) {
    if ($Mask -lt 0x8000) { return 0xF0000 + $Mask }
    return 0x100000 + $Mask - 0x8000
}

function Write-PagedLine([string]$Line, [ref]$Count) {
    Write-Host $Line
    $Count.Value++
    $height = [Math]::Max(4, [Console]::WindowHeight - 2)
    if (-not $NoPager -and ($Count.Value % $height) -eq 0) {
        $answer = Read-Host '-- Enter: next page | q: quit --'
        if ($answer -match '^[qQ]') { throw [System.OperationCanceledException]::new() }
    }
}

function Show-Square([int]$Base, [string]$Title, [ref]$Count) {
    Write-PagedLine $Title $Count
    for ($start = 0; $start -lt 0x100; $start += 0x10) {
        $glyphs = -join ($start..($start + 15) | ForEach-Object {
            [char]::ConvertFromUtf32($Base + $_)
        })
        Write-PagedLine ('{0:X2}-{1:X2}  {2}' -f $start, ($start + 15), $glyphs) $Count
    }
}

function Show-Pua4([ref]$Count) {
    Write-PagedLine 'PUA 4x4 v0.4 RC1: all 65,536 masks' $Count
    Write-PagedLine 'MSB-left rows: 3210 / 7654 / BA98 / FEDC; 16 glyphs per line.' $Count
    for ($start = 0; $start -lt 0x10000; $start += 0x10) {
        $glyphs = -join ($start..($start + 15) | ForEach-Object {
            [char]::ConvertFromUtf32((Get-Pua4Codepoint $_))
        })
        $part = if ($start -lt 0x8000) { 'P0' } else { 'P1' }
        $first = Get-Pua4Codepoint $start
        $last = Get-Pua4Codepoint ($start + 15)
        Write-PagedLine ('{0} mask {1:X4}-{2:X4}  U+{3:X6}-U+{4:X6}  {5}' -f
                         $part, $start, ($start + 15), $first, $last, $glyphs) $Count
    }
}

$lineCount = 0
try {
    if ($Catalog -in @('Square', 'All')) {
        Show-Square 0x2800 'Square Braille official Unicode block U+2800..U+28FF' ([ref]$lineCount)
    }
    if ($Catalog -in @('SquarePua', 'All')) {
        Show-Square 0xE000 'Square Braille compatibility aliases U+E000..U+E0FF' ([ref]$lineCount)
    }
    if ($Catalog -in @('Pua4', 'All')) {
        Show-Pua4 ([ref]$lineCount)
    }
} catch [System.OperationCanceledException] {
    return
}
