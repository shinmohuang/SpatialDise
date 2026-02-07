import pytest

from generator.core.paths import default_output_dir, ensure_dir
from generator.tasks import registry


def test_default_output_dir_uses_3d_prefix_names():
    assert default_output_dir("3d_rotation") == "blender_dataset/3D_rotation"
    assert default_output_dir("3d_projection") == "blender_dataset/3D_projection"
    assert default_output_dir("3d_combination") == "blender_dataset/3D_combination"
    assert default_output_dir("3d_folding") == "blender_dataset/3D_folding"
    assert default_output_dir("3d_shape_finding") == "blender_dataset/3D_shape_finding"
    assert default_output_dir("unknown_task") == "blender_dataset/unknown_task"


def test_ensure_dir_creates_path(tmp_path):
    target = tmp_path / "nested" / "dir"
    out = ensure_dir(str(target))
    assert target.is_dir()
    assert out == str(target)


def test_normalize_task_name_accepts_only_canonical_names():
    assert registry.normalize_task_name("3d_rotation") == "3d_rotation"
    assert registry.normalize_task_name("3d_projection") == "3d_projection"
    with pytest.raises(ValueError):
        registry.normalize_task_name("rotation")
    with pytest.raises(ValueError):
        registry.normalize_task_name("not-a-task")


def test_get_generator_class_loads_dynamic_module(monkeypatch, tmp_path):
    module_file = tmp_path / "dummy_task.py"
    module_file.write_text("class DummyGenerator:\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(registry, "ROOT", tmp_path)
    monkeypatch.setattr(
        registry,
        "TASK_FILES",
        {"dummy_task": ("dummy_task.py", "DummyGenerator")},
    )
    cls = registry.get_generator_class("dummy_task")
    assert cls.__name__ == "DummyGenerator"
