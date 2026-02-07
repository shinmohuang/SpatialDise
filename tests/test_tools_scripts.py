import importlib.util
from pathlib import Path

import pytest


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cleanup_svgs_deletes_svg_only(tmp_path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "tools" / "cleanup_svgs.py",
        "cleanup_svgs_mod",
    )
    (tmp_path / "a.svg").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")

    removed = module.delete_svgs(tmp_path)
    assert removed == 1
    assert not (tmp_path / "a.svg").exists()
    assert (tmp_path / "b.txt").exists()


def test_flatten_outputs_rgb_png(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    module = _load_module(
        Path(__file__).resolve().parents[1] / "tools" / "flatten_lucide.py",
        "flatten_lucide_mod",
    )
    png = tmp_path / "icon.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 128)).save(png)

    processed = module.flatten(tmp_path)
    assert processed == 1

    out = Image.open(png)
    assert out.mode == "RGB"
