import argparse
import subprocess
import sys
from pathlib import Path

from generator.scripts import cache_lucide_icons as script


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])
    args = script.parse_args()
    assert args.prefer_png is True
    assert args.allow_svg_fallback is False


def test_load_icon_list_from_json_file(tmp_path):
    json_file = tmp_path / "icons.json"
    json_file.write_text('["circle", "square"]', encoding="utf-8")
    args = argparse.Namespace(all=False, icons_file=str(json_file), icons=None)
    assert script.load_icon_list(args) == ["circle", "square"]


def test_script_can_run_from_other_workdir(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "generator" / "scripts" / "cache_lucide_icons.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Cache Lucide icons locally" in result.stdout
