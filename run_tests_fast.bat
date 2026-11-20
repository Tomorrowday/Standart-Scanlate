@echo off
chcp 65001 >nul
setlocal
title Manga Translator - Fast Tests
cd /d "%~dp0"

set "PYTHON=venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONIOENCODING=utf-8"

echo ===================================================
echo   Manga Translator - БЫСТРЫЕ ТЕСТЫ
echo   Backend: pytest -m "not heavy"  ^| Frontend: vitest
echo ===================================================
echo.

echo [1/2] Быстрые backend-тесты...
"%PYTHON%" -m pytest -m "not heavy"
if errorlevel 1 (set "BACKEND=FAIL") else (set "BACKEND=PASS")
echo.

echo [2/2] Быстрые frontend-тесты...
cd /d "%~dp0manga_ui"
call npm test
if errorlevel 1 (set "FRONTEND=FAIL") else (set "FRONTEND=PASS")
cd /d "%~dp0"
echo.

echo ===================================================
echo   ИТОГ
echo ===================================================
echo   Backend  (pytest -m "not heavy") : %BACKEND%
echo   Frontend (npm test)              : %FRONTEND%
echo ===================================================

if "%BACKEND%%FRONTEND%"=="PASSPASS" (
    echo   РЕЗУЛЬТАТ: ВСЁ ЗЕЛЁНОЕ
) else (
    echo   РЕЗУЛЬТАТ: ЕСТЬ ОШИБКИ — смотрите вывод выше
)
echo.
pause
endlocal
