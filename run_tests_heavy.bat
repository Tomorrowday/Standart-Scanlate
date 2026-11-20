@echo off
chcp 65001 >nul
setlocal
title Manga Translator - Full / Heavy Tests
cd /d "%~dp0"

set "PYTHON=venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONIOENCODING=utf-8"
set "FAILED=0"

echo ===================================================
echo   Manga Translator - ПОЛНЫЙ ПРОГОН
echo   (быстрые + тяжёлые ML + typecheck + build)
echo ===================================================
echo.

echo [1/5] Быстрые backend-тесты...
"%PYTHON%" -m pytest -m "not heavy"
if errorlevel 1 (set "S1=FAIL" & set /a FAILED+=1) else (set "S1=PASS")
echo.

echo [2/5] Тяжёлые ML/нагрузочные backend-тесты...
"%PYTHON%" -m pytest -m heavy
if errorlevel 1 (set "S2=FAIL" & set /a FAILED+=1) else (set "S2=PASS")
echo.

cd /d "%~dp0manga_ui"

echo [3/5] Быстрые frontend-тесты...
call npm test
if errorlevel 1 (set "S3=FAIL" & set /a FAILED+=1) else (set "S3=PASS")
echo.

echo [4/5] TypeScript typecheck...
call npx tsc --noEmit
if errorlevel 1 (set "S4=FAIL" & set /a FAILED+=1) else (set "S4=PASS")
echo.

echo [5/5] Production build фронтенда...
call npm run build
if errorlevel 1 (set "S5=FAIL" & set /a FAILED+=1) else (set "S5=PASS")
echo.

cd /d "%~dp0"

echo ===================================================
echo   ИТОГ
echo ===================================================
echo   1. Backend fast   (pytest -m "not heavy") : %S1%
echo   2. Backend heavy  (pytest -m heavy)       : %S2%
echo   3. Frontend tests (npm test)              : %S3%
echo   4. Typecheck      (tsc --noEmit)          : %S4%
echo   5. Build          (npm run build)         : %S5%
echo ===================================================

if "%FAILED%"=="0" (
    echo   РЕЗУЛЬТАТ: ВСЁ ЗЕЛЁНОЕ
) else (
    echo   РЕЗУЛЬТАТ: ОШИБОК ЭТАПОВ: %FAILED% — смотрите вывод выше
)
echo.
pause
endlocal
