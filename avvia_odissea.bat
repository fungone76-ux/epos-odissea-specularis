@echo off
REM ============================================================
REM  ODISSEA SPECULARIS — launcher automatico
REM  Posizione: D:\epos_odissea_specularis\avvia_odissea.bat
REM  Doppio clic per giocare (Gemini live + immagini A1111)
REM ============================================================

cd /d "D:\epos_odissea_specularis"

REM --- attiva l'ambiente virtuale ---
if not exist ".venv\Scripts\activate.bat" (
    echo ERRORE: ambiente virtuale non trovato in %CD%\.venv
    echo Crealo con: python -m venv .venv
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

REM --- preflight renderer immagini configurato in .env ---
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "EPOS_RENDER_MODE=" .env 2^>nul') do set "EPOS_RENDER_MODE=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "COMFYUI_BASE_URL=" .env 2^>nul') do set "COMFYUI_BASE_URL=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "EPOS_COMFY_URL=" .env 2^>nul') do set "EPOS_COMFY_URL=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "A1111_BASE_URL=" .env 2^>nul') do set "A1111_BASE_URL=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "EPOS_A1111_URL=" .env 2^>nul') do set "EPOS_A1111_URL=%%B"

if /i "%EPOS_RENDER_MODE%"=="comfy" (
    if "%COMFYUI_BASE_URL%"=="" set "COMFYUI_BASE_URL=%EPOS_COMFY_URL%"
    if not "%COMFYUI_BASE_URL%"=="" (
        curl -s --max-time 5 "%COMFYUI_BASE_URL%/system_stats" >nul 2>&1
        if errorlevel 1 (
            echo.
            echo  ATTENZIONE: ComfyUI non risponde su %COMFYUI_BASE_URL%
            echo  Le immagini NON verranno generate. Tieni aperto il tunnel SSH e riprova,
            echo  oppure premi un tasto per giocare comunque senza immagini.
            echo.
            pause
        )
    )
) else if /i "%EPOS_RENDER_MODE%"=="a1111" (
    if "%A1111_BASE_URL%"=="" set "A1111_BASE_URL=%EPOS_A1111_URL%"
    if not "%A1111_BASE_URL%"=="" (
        curl -s --max-time 5 "%A1111_BASE_URL%/sdapi/v1/sd-models" >nul 2>&1
        if errorlevel 1 (
            echo.
            echo  ATTENZIONE: Forge/A1111 non risponde su %A1111_BASE_URL%
            echo  Le immagini NON verranno generate. Tieni aperto il tunnel SSH e riprova,
            echo  oppure premi un tasto per giocare comunque senza immagini.
            echo.
            pause
        )
    )
)

REM --- avvia il gioco: GM Gemini live + renderer da EPOS_RENDER_MODE ---
python tools\play_odyssey_gui.py --live

REM --- se il gioco esce con errore, tieni aperta la finestra per leggerlo ---
if errorlevel 1 (
    echo.
    echo  Il gioco e uscito con un errore. Leggi il messaggio qui sopra.
    pause
)
