from generator.cli import config_generate as cg


def test_load_config_file_supports_json_and_yaml(tmp_path):
    json_path = tmp_path / "cfg.json"
    json_path.write_text('{"task": "3d_rotation", "num_questions": 2}', encoding="utf-8")
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text("task: 3d_rotation\nnum_questions: 3\n", encoding="utf-8")

    json_cfg = cg._load_config_file(str(json_path))
    yaml_cfg = cg._load_config_file(str(yaml_path))

    assert json_cfg["num_questions"] == 2
    assert yaml_cfg["num_questions"] == 3


def test_iter_jobs_merges_defaults():
    raw = {
        "defaults": {"num_questions": 5, "image_resolution": [640, 480]},
        "tasks": [{"task": "3d_rotation"}, {"task": "3d_projection", "num_questions": 2}],
    }
    jobs = list(cg._iter_jobs(raw))
    assert jobs[0]["num_questions"] == 5
    assert jobs[1]["num_questions"] == 2


def test_prepare_generator_config_strips_non_generator_keys():
    cfg = cg._prepare_generator_config(
        {
            "task": "3d_rotation",
            "output_dir": "out",
            "image_resolution": [800, 600],
            "num_questions": 7,
            "preset": "hard",
        },
        "3d_rotation",
    )
    assert "task" not in cfg
    assert "output_dir" not in cfg
    assert "preset" not in cfg
    assert cfg["image_resolution"] == (800, 600)
    assert cfg["num_questions"] == 7
