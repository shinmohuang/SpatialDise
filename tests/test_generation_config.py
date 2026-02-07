from generator.core.config import GenerationConfig


def test_generation_config_from_dict_extracts_extra():
    cfg = GenerationConfig.from_dict(
        {
            "num_questions": 5,
            "image_resolution": (320, 240),
            "use_gpu": False,
            "difficulty": "hard",
            "custom_seed": 123,
        }
    )

    assert cfg.num_questions == 5
    assert cfg.image_resolution == (320, 240)
    assert cfg.use_gpu is False
    assert cfg.extra == {"difficulty": "hard", "custom_seed": 123}
