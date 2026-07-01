"""DashScope/Qwen provider registration tests."""

from __future__ import annotations

from coffeebench_ocl.qwen_model import (
    DashScopeQwenModel,
    build_qwen_model,
    install_qwen_provider,
    is_qwen_model_id,
    _clean_env_value,
)


def test_qwen_model_ids_are_recognized() -> None:
    assert is_qwen_model_id("qwen-plus")
    assert is_qwen_model_id("qwen3-max")
    assert is_qwen_model_id("qwen/qwen-plus")
    assert is_qwen_model_id("dashscope/qwen-plus")
    assert not is_qwen_model_id("gpt-5.5")
    assert not is_qwen_model_id("moonshotai/kimi-k2.6")


def test_build_qwen_model_strips_namespace_and_suffix() -> None:
    model = build_qwen_model("dashscope/qwen-plus-no-thinking")

    assert isinstance(model, DashScopeQwenModel)
    assert model.provider_model == "qwen-plus"
    assert model.model == "qwen/qwen-plus"


def test_install_qwen_provider_patches_coffeebench_registry() -> None:
    install_qwen_provider()

    import coffeebench.main as coffee_main
    import coffeebench.models as coffee_models

    model_from_models = coffee_models.get_model("qwen-plus")
    model_from_main = coffee_main.get_model("qwen-plus")

    assert isinstance(model_from_models, DashScopeQwenModel)
    assert isinstance(model_from_main, DashScopeQwenModel)
    assert coffee_models.get_model("passive").model == "passive"


def test_clean_env_value_strips_copy_paste_quotes() -> None:
    assert _clean_env_value(" “sk-test” ") == "sk-test"
    assert _clean_env_value("'https://dashscope.aliyuncs.com/compatible-mode/v1'") == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
