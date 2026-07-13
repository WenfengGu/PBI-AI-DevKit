@echo off
chcp 65001 >nul
title Claude Power BI MCP - Setup

echo ============================================================
echo   Claude Power BI MCP Server - One-Click Setup
echo ============================================================
echo.

REM Step 1: Check Python
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.11+ from:
    echo   https://www.python.org/downloads/
    echo   IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)
python --version
echo   OK

REM Step 2: Install pythonnet
echo.
echo [2/5] Installing pythonnet...
pip install pythonnet -q 2>&1
if errorlevel 1 (
    pip install pythonnet --user -q 2>&1
)
python -c "import clr; print('OK')" 2>nul
if errorlevel 1 (
    echo [ERROR] pythonnet installation failed.
    echo Please run manually: pip install pythonnet
    pause
    exit /b 1
)
echo   OK

REM Step 3: Auto-detect Power BI Desktop and generate .mcp.json
echo.
echo [3/5] Detecting Power BI Desktop and generating config...
python -c @"
import os, json, sys
from pathlib import Path

# Auto-detect PBI path
pbi_bin = None
for base in [r'D:\Program Files', r'C:\Program Files', r'C:\Program Files (x86)']:
    p = Path(base) / 'Microsoft Power BI Desktop' / 'bin'
    if (p / 'Microsoft.PowerBI.AdomdClient.dll').exists():
        pbi_bin = str(p)
        break

if not pbi_bin:
    print('  WARNING: Power BI Desktop not detected automatically.')
    print('  If you have Power BI installed, please configure .mcp.json manually.')
    sys.exit(0)

# Generate .mcp.json
install_dir = os.path.dirname(os.path.abspath(__file__))
mcp_config = {
    'mcpServers': {
        'claude-powerbi': {
            'command': 'python',
            'args': [install_dir + '\\\\server.py'],
            'env': {
                'PATH': f'{pbi_bin};${{PATH}}'
            }
        }
    }
}

mcp_path = os.path.join(install_dir, '.mcp.json')
with open(mcp_path, 'w', encoding='utf-8') as f:
    json.dump(mcp_config, f, indent=2)

print(f'  PBI bin: {pbi_bin}')
print(f'  Config:  {mcp_path}')
"@ 2>nul
if errorlevel 1 (
    echo [WARNING] Could not auto-generate .mcp.json.
    echo Please manually configure .mcp.json using the template.
) else (
    echo   OK - .mcp.json generated
)

REM Step 4: Install Skill
echo.
echo [4/5] Installing Claude Code Skill...
set "SKILL_SRC=%~dp0.claude\skills\powerbi-model.md"
set "SKILL_DST=%USERPROFILE%\.claude\skills\powerbi-model.md"
if exist "%SKILL_SRC%" (
    if not exist "%USERPROFILE%\.claude\skills" mkdir "%USERPROFILE%\.claude\skills"
    copy /y "%SKILL_SRC%" "%SKILL_DST%" >nul 2>&1
    echo   OK - Skill installed to %SKILL_DST%
) else (
    echo   WARNING: Skill file not found, skipping
)

REM Step 5: Done
echo.
echo [5/5] Verifying setup...
python -c "from ssas_client import find_powerbi_bin; find_powerbi_bin(); print('OK')" 2>nul
if errorlevel 1 (
    echo [WARNING] Verification failed. Please check your Power BI installation.
) else (
    echo   OK
)

echo.
echo ============================================================
echo   SETUP COMPLETE!
echo ============================================================
echo.
echo   Next steps:
echo   1. Open a PBIX file in Power BI Desktop
echo   2. Run: python test_connection.py
echo   3. Copy .mcp.json to your Claude Code project root
echo   4. Restart Claude Code
echo.
echo   Need help? See README.md
echo.
pause