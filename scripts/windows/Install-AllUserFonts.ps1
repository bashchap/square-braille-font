[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$FontDirectory = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
$RegistryPath = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
$Fonts = @(
    @{
        File = 'fonts\current\Square-Braille-Unicode-Text-Seamless.ttf'
        Name = 'Square Braille Unicode Text Seamless (TrueType)'
    },
    @{
        File = 'fonts\candidates\pua-4x4-v0.4-rc1\PUA4x4Part0V04Candidate3.ttf'
        Name = 'PUA 4x4 Part 0 v0.4 Candidate 3 (TrueType)'
    },
    @{
        File = 'fonts\candidates\pua-4x4-v0.4-rc1\PUA4x4Part1V04Candidate3.ttf'
        Name = 'PUA 4x4 Part 1 v0.4 Candidate 3 (TrueType)'
    }
)

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ProjectUserFontLoader {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    public static extern int AddFontResourceEx(string file, uint flags, IntPtr reserved);
}
'@

New-Item -ItemType Directory -Force -Path $FontDirectory | Out-Null
New-Item -Path $RegistryPath -Force | Out-Null
foreach ($font in $Fonts) {
    $source = Join-Path $Root $font.File
    if (-not (Test-Path $source)) { throw "Font not found: $source" }
    $destination = Join-Path $FontDirectory ([IO.Path]::GetFileName($source))
    Copy-Item -Force $source $destination
    New-ItemProperty -Path $RegistryPath -Name $font.Name -Value $destination `
        -PropertyType String -Force | Out-Null
    [void][ProjectUserFontLoader]::AddFontResourceEx(
        $destination, 0x10, [IntPtr]::Zero)
    Write-Host "Installed: $destination"
    Get-FileHash -Algorithm SHA256 $destination | Format-List
}

Write-Host 'Restart terminal applications so they rebuild their user-font lists.'
Write-Host 'Square profile: Square Braille Unicode Text Seamless'
Write-Host 'PUA 4x4 fallback order: Square Braille text, PUA4 Part 0, PUA4 Part 1'
