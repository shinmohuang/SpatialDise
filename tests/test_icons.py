from pathlib import Path

from generator.core import icons


def test_write_license_note_creates_file(monkeypatch, tmp_path):
    monkeypatch.setattr(icons, "ASSETS_ROOT", tmp_path)
    monkeypatch.setattr(icons, "CUSTOM_ASSETS_ROOT", tmp_path / "customize")
    monkeypatch.setattr(icons, "LICENSE_PATH", tmp_path / "LICENSE_LUCIDE.txt")

    icons._write_license_note()

    assert icons.LICENSE_PATH.exists()
    assert "Lucide Icons" in icons.LICENSE_PATH.read_text(encoding="utf-8")


def test_ensure_lucide_icons_uses_existing_png_without_download(monkeypatch, tmp_path):
    monkeypatch.setattr(icons, "ASSETS_ROOT", tmp_path)
    monkeypatch.setattr(icons, "CUSTOM_ASSETS_ROOT", tmp_path / "customize")
    monkeypatch.setattr(icons, "LICENSE_PATH", tmp_path / "LICENSE_LUCIDE.txt")
    (tmp_path / "circle.png").write_bytes(b"png")

    available = icons.ensure_lucide_icons(
        icon_names=["circle"], download=False, prefer_png=True
    )

    assert available == [str(tmp_path / "circle.png")]


def test_ensure_lucide_icons_prefers_customize_icon(monkeypatch, tmp_path):
    lucide_root = tmp_path / "lucide"
    custom_root = tmp_path / "customize"
    lucide_root.mkdir(parents=True, exist_ok=True)
    custom_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(icons, "ASSETS_ROOT", lucide_root)
    monkeypatch.setattr(icons, "CUSTOM_ASSETS_ROOT", custom_root)
    monkeypatch.setattr(icons, "LICENSE_PATH", lucide_root / "LICENSE_LUCIDE.txt")

    (lucide_root / "circle.png").write_bytes(b"lucide")
    (custom_root / "circle.png").write_bytes(b"custom")

    available = icons.ensure_lucide_icons(
        icon_names=["circle"], download=False, prefer_png=True
    )

    assert available == [str(custom_root / "circle.png")]


def test_resolve_task_icons_uses_customize_when_icon_names_unset(monkeypatch, tmp_path):
    lucide_root = tmp_path / "lucide"
    custom_root = tmp_path / "customize"
    lucide_root.mkdir(parents=True, exist_ok=True)
    custom_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(icons, "ASSETS_ROOT", lucide_root)
    monkeypatch.setattr(icons, "CUSTOM_ASSETS_ROOT", custom_root)
    monkeypatch.setattr(icons, "LICENSE_PATH", lucide_root / "LICENSE_LUCIDE.txt")

    (custom_root / "a.png").write_bytes(b"a")
    (custom_root / "b.png").write_bytes(b"b")

    available = icons.resolve_task_icons(
        icon_names=None, download=False, prefer_png=True, allow_svg_fallback=False
    )

    assert available == [str(custom_root / "a.png"), str(custom_root / "b.png")]


def test_select_icons_deterministic_is_stable():
    icon_list = ["a", "b", "c", "d"]
    first = icons.select_icons_deterministic(42, icon_list, 3)
    second = icons.select_icons_deterministic(42, icon_list, 3)
    assert first == second
