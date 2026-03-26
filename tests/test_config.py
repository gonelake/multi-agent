"""
test_config.py — Config 单元测试

覆盖：
- ReviewConfig 默认值和校验
- LLMClientConfig 参数校验
- AgentConfig 温度参数校验
- SearchConfig 参数校验
- WorkflowConfig 参数校验
- CliDefaults 参数校验
"""
import pytest
from config import (
    ReviewConfig, LLMClientConfig, AgentConfig,
    SearchConfig, WorkflowConfig, CliDefaults, LLMConfig,
)


class TestReviewConfigDefaults:
    def test_default_pass_threshold(self):
        cfg = ReviewConfig()
        assert cfg.pass_threshold == 85

    def test_default_dimension_weights_sum_to_100(self):
        cfg = ReviewConfig()
        assert cfg.total_score() == 100

    def test_default_has_five_dimensions(self):
        cfg = ReviewConfig()
        expected = {"content_insight", "readability", "title_appeal", "structure_flow", "accuracy"}
        assert set(cfg.dimension_weights.keys()) == expected

    def test_dimension_weights_are_independent_per_instance(self):
        """每个实例的 dimension_weights 应是不同的 dict 对象"""
        cfg1 = ReviewConfig()
        cfg2 = ReviewConfig()
        assert cfg1.dimension_weights is not cfg2.dimension_weights


class TestReviewConfigValidation:
    def test_pass_threshold_too_low_raises(self):
        with pytest.raises(ValueError, match="pass_threshold"):
            ReviewConfig(pass_threshold=0)

    def test_pass_threshold_too_high_raises(self):
        with pytest.raises(ValueError, match="pass_threshold"):
            ReviewConfig(pass_threshold=101)

    def test_dimension_weights_not_sum_to_100_raises(self):
        with pytest.raises(ValueError, match="dimension_weights"):
            ReviewConfig(dimension_weights={"a": 50, "b": 40})  # sum=90

    def test_valid_boundary_pass_threshold(self):
        assert ReviewConfig(pass_threshold=1).pass_threshold == 1
        assert ReviewConfig(pass_threshold=100).pass_threshold == 100


class TestReviewConfigCustom:
    def test_custom_pass_threshold(self):
        cfg = ReviewConfig(pass_threshold=90)
        assert cfg.pass_threshold == 90

    def test_pass_threshold_75(self):
        cfg = ReviewConfig(pass_threshold=75)
        assert cfg.pass_threshold == 75


class TestReviewConfigGeneratedText:
    def test_score_description_contains_threshold(self):
        cfg = ReviewConfig(pass_threshold=85)
        desc = cfg.score_description()
        assert "85" in desc

    def test_score_description_custom_threshold(self):
        cfg = ReviewConfig(pass_threshold=90)
        desc = cfg.score_description()
        assert "90" in desc

    def test_dimension_prompt_contains_all_dimensions(self):
        cfg = ReviewConfig()
        prompt = cfg.dimension_prompt()
        assert "内容洞察" in prompt
        assert "可读性" in prompt
        assert "标题吸引力" in prompt
        assert "结构流畅" in prompt
        assert "事实准确性" in prompt

    def test_dimension_prompt_contains_scores(self):
        cfg = ReviewConfig()
        prompt = cfg.dimension_prompt()
        # 默认权重 30/25/20/15/10 应都出现
        assert "30" in prompt
        assert "25" in prompt
        assert "20" in prompt
        assert "15" in prompt
        assert "10" in prompt


class TestLLMClientConfigValidation:
    def test_timeout_zero_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            LLMClientConfig(timeout=0)

    def test_timeout_negative_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            LLMClientConfig(timeout=-1.0)

    def test_max_tokens_zero_raises(self):
        with pytest.raises(ValueError, match="max_tokens"):
            LLMClientConfig(max_tokens=0)

    def test_temperature_too_high_raises(self):
        with pytest.raises(ValueError, match="default_temperature"):
            LLMClientConfig(default_temperature=2.1)

    def test_temperature_negative_raises(self):
        with pytest.raises(ValueError, match="default_temperature"):
            LLMClientConfig(default_temperature=-0.1)

    def test_max_retries_negative_raises(self):
        with pytest.raises(ValueError, match="max_retries"):
            LLMClientConfig(max_retries=-1)

    def test_valid_defaults(self):
        cfg = LLMClientConfig()
        assert cfg.timeout == 120.0
        assert cfg.max_tokens == 8192
        assert cfg.max_retries == 2


class TestAgentConfigValidation:
    def test_temperature_out_of_range_raises(self):
        with pytest.raises(ValueError, match="researcher_with_search"):
            AgentConfig(researcher_with_search=2.1)

    def test_reviewer_temp_negative_raises(self):
        with pytest.raises(ValueError, match="reviewer"):
            AgentConfig(reviewer=-0.1)

    def test_valid_defaults(self):
        cfg = AgentConfig()
        assert 0.0 <= cfg.researcher_with_search <= 2.0
        assert 0.0 <= cfg.writer_draft <= 2.0
        assert 0.0 <= cfg.reviewer <= 2.0


class TestSearchConfigValidation:
    def test_max_results_zero_raises(self):
        with pytest.raises(ValueError, match="max_results"):
            SearchConfig(max_results=0)

    def test_default_days_zero_raises(self):
        with pytest.raises(ValueError, match="default_days"):
            SearchConfig(default_days=0)

    def test_valid_defaults(self):
        cfg = SearchConfig()
        assert cfg.max_results == 5
        assert cfg.default_days == 7


class TestWorkflowConfigValidation:
    def test_max_revisions_negative_raises(self):
        with pytest.raises(ValueError, match="max_revisions"):
            WorkflowConfig(max_revisions=-1)

    def test_zero_revisions_valid(self):
        cfg = WorkflowConfig(max_revisions=0)
        assert cfg.max_revisions == 0


class TestCliDefaultsValidation:
    def test_pass_threshold_out_of_range_raises(self):
        with pytest.raises(ValueError, match="pass_threshold"):
            CliDefaults(pass_threshold=150)

    def test_word_count_zero_raises(self):
        with pytest.raises(ValueError, match="word_count"):
            CliDefaults(word_count=0)

    def test_hotspot_count_zero_raises(self):
        with pytest.raises(ValueError, match="hotspot_count"):
            CliDefaults(hotspot_count=0)

    def test_valid_defaults(self):
        cfg = CliDefaults()
        assert cfg.pass_threshold == 85
        assert cfg.word_count == 1000


class TestLLMConfigValidation:
    def test_invalid_api_style_raises(self):
        with pytest.raises(ValueError, match="api_style"):
            LLMConfig(api_key="key", api_style="invalid")

    def test_valid_api_styles(self):
        assert LLMConfig(api_key="key", api_style="anthropic").api_style == "anthropic"
        assert LLMConfig(api_key="key", api_style="openai").api_style == "openai"
