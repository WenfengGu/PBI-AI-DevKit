# Claude Power BI MCP - One-Line Deploy
# ======================================
# Save this file anywhere, then tell Claude:
#   "Run this deploy script: d:\path\to\deploy.ps1"
#
# Or just tell Claude:
#   "Download and deploy PBI-AI-DevKit from https://github.com/XXX/PBI-AI-DevKit"
#
# Claude will execute all steps automatically.

param(
    [string]$DownloadUrl = "https://github.com/WenfengGu/PBI-AI-DevKit/archive/refs/heads/main.zip",
    [string]$InstallDir = "$env:USERPROFILE\PBI-AI-DevKit"
)

$ErrorActionPreference = "Stop"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Claude Power BI MCP Server - GitHub Auto Deploy" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Download
Write-Host "[1/5] Downloading from GitHub..." -ForegroundColor Yellow
$zipPath = "$env:TEMP\PBI-AI-DevKit.zip"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
    Write-Host "  OK - Downloaded ($('{0:N0}' -f (Get-Item $zipPath).Length) bytes)" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Download failed: $_" -ForegroundColor Red
    Write-Host "  Check the URL: $DownloadUrl" -ForegroundColor Red
    exit 1
}

# Step 2: Extract
Write-Host "[2/5] Extracting..." -ForegroundColor Yellow
$extractPath = "$env:TEMP\PBI-AI-DevKit-Extract"
if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

# GitHub wraps in a folder named "repo-branch", move contents out
$innerDir = Get-ChildItem $extractPath -Directory | Select-Object -First 1
if ($innerDir) {
    Move-Item $innerDir.FullName $InstallDir -Force
} else {
    Move-Item "$extractPath\*" $InstallDir -Force
}
Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue
Write-Host "  OK - Extracted to $InstallDir" -ForegroundColor Green

# Step 3: Install Python dependency
Write-Host "[3/5] Installing pythonnet..." -ForegroundColor Yellow
try {
    pip install pythonnet -q 2>&1 | Out-Null
    python -c "import clr; print('OK')"
    Write-Host "  OK - pythonnet installed" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: pip install failed, trying --user..." -ForegroundColor Yellow
    pip install pythonnet --user -q 2>&1 | Out-Null
}

# Step 4: Auto-detect Power BI and verify
Write-Host "[4/5] Detecting Power BI Desktop..." -ForegroundColor Yellow
$pbiPath = $null
# Check running process
$pbiProc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pbiProc -and $pbiProc.Path) {
    $pbiBin = Split-Path $pbiProc.Path -Parent
    if (Test-Path "$pbiBin\Microsoft.PowerBI.AdomdClient.dll") {
        $pbiPath = $pbiBin
    }
}
# Fallback: check common paths
if (-not $pbiPath) {
    $commonPaths = @(
        "D:\Program Files\Microsoft Power BI Desktop\bin",
        "C:\Program Files\Microsoft Power BI Desktop\bin",
        "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path "$p\Microsoft.PowerBI.AdomdClient.dll") {
            $pbiPath = $p
            break
        }
    }
}
if ($pbiPath) {
    Write-Host "  OK - Found: $pbiPath" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Power BI Desktop not detected." -ForegroundColor Yellow
    Write-Host "  Please install Power BI Desktop and open a PBIX file." -ForegroundColor Yellow
    $pbiPath = "C:\Program Files\Microsoft Power BI Desktop\bin"
}

# Step 5: Write .mcp.json
Write-Host "[5/6] Writing Claude Code config..." -ForegroundColor Yellow
$installDirEscaped = $InstallDir -replace '\\', '\\'
$mcpJson = @"
{
  "mcpServers": {
    "claude-powerbi": {
      "command": "python",
      "args": ["$installDirEscaped\\server.py"],
      "env": {
        "PATH": "$($pbiPath -replace '\\','\\');`${PATH}"
      }
    }
  }
}
"@
$mcpJsonPath = "$InstallDir\.mcp.json"
$mcpJson | Out-File -FilePath $mcpJsonPath -Encoding utf8
Write-Host "  OK - Config written to $mcpJsonPath" -ForegroundColor Green

# Step 6: Install Skill
Write-Host "[6/6] Installing Claude Code Skill..." -ForegroundColor Yellow
$skillDir = "$env:USERPROFILE\.claude\skills"
if (-not (Test-Path $skillDir)) { New-Item -ItemType Directory -Force $skillDir | Out-Null }
$skillSrc = "$InstallDir\.claude\skills\powerbi-model.md"
if (Test-Path $skillSrc) {
    Copy-Item $skillSrc "$skillDir\powerbi-model.md" -Force
    Write-Host "  OK - Skill installed to $skillDir\powerbi-model.md" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Skill file not found, skipping" -ForegroundColor Yellow
}

# Cleanup
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

# Done
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Folder:   $InstallDir" -ForegroundColor White
Write-Host "  Config:   $mcpJsonPath" -ForegroundColor White
Write-Host "  PBI Path: $pbiPath" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open a PBIX file in Power BI Desktop" -ForegroundColor White
Write-Host "  2. Test: python `"$InstallDir\test_connection.py`"" -ForegroundColor White
Write-Host "  3. Copy $mcpJsonPath to your Claude Code project root" -ForegroundColor White
Write-Host ""

# Return info for Claude to use
return @{
    InstallDir = $InstallDir
    McpJsonPath = $mcpJsonPath
    PbiBinPath = $pbiPath
}