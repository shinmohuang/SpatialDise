from pathlib import Path

from generator.core import icons


def test_write_license_note_creates_file(monkeypatch, tmp_path):
    monkeypatch.setattr(icons, "ASSETS_ROOT", tmp_path)
    monkeypatch.setattr(icons, "LICENSE_PATH", tmp_path / "LICENSE_LUCIDE.txt")

    icons._write_license_note()

    assert icons.LICENSE_PATH.exists()
    assert "Lucide Icons" in icons.LICENSE_PATH.read_text(encoding="utf-8")


def test_ensure_lucide_icons_uses_existing_png_without_download(monkeypatch, tmp_path):
    monkeypatch.setattr(icons, "ASSETS_ROOT", tmp_path)
    monkeypatch.setattr(icons, "LICENSE_PATH", tmp_path / "LICENSE_LUCIDE.txt")
    (tmp_path / "circle.png").write_bytes(b"png")

    available = icons.ensure_lucide_icons(
        icon_names=["circle"], download=False, prefer_png=True
    )

    assert available == [str(tmp_path / "circle.png")]


def test_select_icons_deterministic_is_stable():
    icon_list = ["a", "b", "c", "d"]
    first = icons.select_icons_deterministic(42, icon_list, 3)
    second = icons.select_icons_deterministic(42, icon_list, 3)
    assert first == second
