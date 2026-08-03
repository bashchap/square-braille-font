[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$FontName = 'Square-Braille-Unicode-Text-Seamless.ttf'
$DisplayName = 'Square Braille Unicode Text Seamless (TrueType)'
$Source = Join-Path $Root "fonts\current\$FontName"
$FontDirectory = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
$Destination = Join-Path $FontDirectory $FontName
$RegistryPath = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'

if (-not (Test-Path $Source)) {
    throw "Font not found: $Source"
}

New-Item -ItemType Directory -Force -Path $FontDirectory | Out-Null
Copy-Item -Force $Source $Destination
New-Item -Path $RegistryPath -Force | Out-Null
New-ItemProperty -Path $RegistryPath -Name $DisplayName -Value $Destination `
    -PropertyType String -Force | Out-Null

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class UserFontLoader {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    public static extern int AddFontResourceEx(string file, uint flags, IntPtr reserved);
}
'@
[void][UserFontLoader]::AddFontResourceEx($Destination, 0x10, [IntPtr]::Zero)

Write-Host "Installed: $Destination"
Write-Host 'Restart Windows Terminal, then select "Square Braille Unicode Text Seamless".'

