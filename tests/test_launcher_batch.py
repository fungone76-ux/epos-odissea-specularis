from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "avvia_odissea.bat"


def _launcher_text() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_preflight_branches_on_render_mode():
    text = _launcher_text()

    assert 'if /i "%EPOS_RENDER_MODE%"=="comfy"' in text
    assert 'else if /i "%EPOS_RENDER_MODE%"=="a1111"' in text
    assert '"%COMFYUI_BASE_URL%/system_stats"' in text
    assert '"%A1111_BASE_URL%/sdapi/v1/sd-models"' in text
    assert "ComfyUI non risponde su %COMFYUI_BASE_URL%" in text
    assert "Forge/A1111 non risponde su %A1111_BASE_URL%" in text


def test_launcher_uses_configured_urls_without_forge_hardcoded_fallback():
    text = _launcher_text()

    assert 'findstr /b /i "COMFYUI_BASE_URL=" .env' in text
    assert 'findstr /b /i "EPOS_COMFY_URL=" .env' in text
    assert 'findstr /b /i "A1111_BASE_URL=" .env' in text
    assert 'findstr /b /i "EPOS_A1111_URL=" .env' in text
    assert "set A1111_BASE_URL=http://127.0.0.1:17860" not in text
    assert "/sdapi/v1/options" not in text


def test_launcher_does_not_force_render_mode_after_env_load():
    lines = _launcher_text().splitlines()
    render_mode_sets = [
        line.strip()
        for line in lines
        if line.strip().lower().startswith("set ")
        and "EPOS_RENDER_MODE".lower() in line.lower()
    ]

    assert render_mode_sets == []
