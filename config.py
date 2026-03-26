"""
config.py — 系统配置模块

所有可调参数的唯一来源（Single Source of Truth）。
优先级：CLI 参数 > config.py > 环境变量

使用方式：
  - 调整默认值：直接修改下方各 Config 类中的字段
  - 临时覆盖：通过 CLI 参数（main.py）传入
  - 环境变量：作为补充 fallback（敏感信息如 API Key 必须通过此方式）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


# ══════════════════════════════════════════════
# LLM 连接配置
# ══════════════════════════════════════════════

@dataclass
class LLMConfig:
    """
    LLM API 连接信息。

    ⚠️  api_key 不在此处存储真实值，必须通过 .env 或环境变量 LLM_API_KEY 提供。
    其余参数可直接在此修改作为默认值。
    """
    api_key:   str = ""                                  # 必须通过环境变量设置
    base_url:  str = "https://api.kimi.com/coding/v1"
    model:     str = "kimi-for-coding"
    api_style: str = "anthropic"                         # "anthropic" 或 "openai"

    def __post_init__(self):
        if self.api_style not in ("anthropic", "openai"):
            raise ValueError(f"api_style 必须是 'anthropic' 或 'openai'，当前值: {self.api_style!r}")

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """
        读取 LLM 配置，优先级：环境变量 > 此处默认值。
        api_key 缺失时抛出异常（快速失败，避免后续调用时才报错）。
        """
        defaults = cls.__new__(cls)
        object.__setattr__(defaults, "api_key", "")
        object.__setattr__(defaults, "base_url", "https://api.kimi.com/coding/v1")
        object.__setattr__(defaults, "model", "kimi-for-coding")
        object.__setattr__(defaults, "api_style", "anthropic")

        api_key = os.environ.get("LLM_API_KEY", "")
        if not api_key:
            raise ValueError(
                "❌ 未配置 LLM API Key。\n"
                "   请在项目根目录创建 .env 文件并设置：\n"
                "   LLM_API_KEY=your-api-key\n"
                "   参考 .env.example 文件。"
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL", defaults.base_url),
            model=os.environ.get("LLM_MODEL", defaults.model),
            api_style=os.environ.get("LLM_API_STYLE", defaults.api_style),
        )


# ══════════════════════════════════════════════
# LLM 客户端参数
# ══════════════════════════════════════════════

@dataclass
class LLMClientConfig:
    """
    LLM API 客户端的运行时参数。
    支持通过环境变量覆盖：LLM_TIMEOUT, LLM_MAX_TOKENS, LLM_MAX_RETRIES, LLM_ANTHROPIC_VERSION
    """
    timeout:             float = 120.0        # HTTP 请求超时（秒）
    max_tokens:          int   = 8192         # 单次响应最大 token 数
    default_temperature: float = 0.7          # 未指定 temperature 时的默认值
    max_retries:         int   = 2            # JSON 解析失败时的最大重试次数
    anthropic_version:   str   = "2023-06-01" # Anthropic API 版本头

    def __post_init__(self):
        if self.timeout <= 0:
            raise ValueError(f"timeout 必须大于 0，当前值: {self.timeout}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens 必须大于 0，当前值: {self.max_tokens}")
        if not (0.0 <= self.default_temperature <= 2.0):
            raise ValueError(f"default_temperature 必须在 0.0-2.0 范围内，当前值: {self.default_temperature}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries 必须 >= 0，当前值: {self.max_retries}")

    @classmethod
    def from_env(cls) -> "LLMClientConfig":
        """从环境变量读取客户端参数，未设置则使用默认值。"""
        defaults = cls()
        return cls(
            timeout=float(os.environ.get("LLM_TIMEOUT", defaults.timeout)),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", defaults.max_tokens)),
            default_temperature=float(os.environ.get("LLM_TEMPERATURE", defaults.default_temperature)),
            max_retries=int(os.environ.get("LLM_MAX_RETRIES", defaults.max_retries)),
            anthropic_version=os.environ.get("LLM_ANTHROPIC_VERSION", defaults.anthropic_version),
        )


# ══════════════════════════════════════════════
# 智能体温度参数
# ══════════════════════════════════════════════

@dataclass
class AgentConfig:
    """
    各智能体 LLM 调用的 temperature 参数。

    命名规范：{agent}_{mode}
    - 值越小：输出越确定性（适合分析、审校）
    - 值越大：输出越多样性（适合创意、头脑风暴）
    """
    # ResearcherAgent
    researcher_with_search: float = 0.3  # 有真实搜索结果参考，降低随机性
    researcher_fallback:    float = 0.8  # 纯 LLM 生成，需要更多创意

    # WriterAgent
    writer_eval:    float = 0.1  # 评估反馈价值，需要高确定性判断
    writer_draft:   float = 0.7  # 初稿撰写，平衡创意与质量
    writer_revise:  float = 0.6  # 修改稿件，略低于初稿以保持一致性

    # ReviewerAgent
    reviewer: float = 0.3  # 审校评分，需要稳定一致的评判标准

    def __post_init__(self):
        fields = {
            "researcher_with_search": self.researcher_with_search,
            "researcher_fallback":    self.researcher_fallback,
            "writer_eval":            self.writer_eval,
            "writer_draft":           self.writer_draft,
            "writer_revise":          self.writer_revise,
            "reviewer":               self.reviewer,
        }
        for name, value in fields.items():
            if not (0.0 <= value <= 2.0):
                raise ValueError(f"AgentConfig.{name} 必须在 0.0-2.0 范围内，当前值: {value}")


# ══════════════════════════════════════════════
# 搜索参数
# ══════════════════════════════════════════════

@dataclass
class SearchConfig:
    """
    DuckDuckGo 新闻搜索参数。
    """
    max_results:         int  = 5    # 单次搜索最大返回条数
    default_days:        int  = 7    # 默认搜索时间窗口（天）
    results_per_query:   int  = 3    # search_multi 中每个关键词的返回条数
    content_preview_len: int  = 300  # 格式化时摘要内容的截断长度

    # DuckDuckGo timelimit 参数映射（天数 → API 参数）
    timelimit_map: Dict[int, str] = field(
        default_factory=lambda: {1: "d", 7: "w", 30: "m", 365: "y"}
    )

    def __post_init__(self):
        if self.max_results <= 0:
            raise ValueError(f"max_results 必须大于 0，当前值: {self.max_results}")
        if self.default_days <= 0:
            raise ValueError(f"default_days 必须大于 0，当前值: {self.default_days}")
        if self.results_per_query <= 0:
            raise ValueError(f"results_per_query 必须大于 0，当前值: {self.results_per_query}")
        if self.content_preview_len <= 0:
            raise ValueError(f"content_preview_len 必须大于 0，当前值: {self.content_preview_len}")

    def timelimit(self, days: int) -> str:
        """将天数转换为 DuckDuckGo timelimit 参数值，未匹配时默认周。"""
        return self.timelimit_map.get(days, "w")


# ══════════════════════════════════════════════
# 工作流参数
# ══════════════════════════════════════════════

@dataclass
class WorkflowConfig:
    """
    Orchestrator 工作流参数。
    """
    max_revisions:    int = 2   # 审校-修改循环的最大轮次
    threshold_buffer: int = 15  # 大幅修改线 = pass_threshold - threshold_buffer

    def __post_init__(self):
        if self.max_revisions < 0:
            raise ValueError(f"max_revisions 必须 >= 0，当前值: {self.max_revisions}")
        if self.threshold_buffer < 0:
            raise ValueError(f"threshold_buffer 必须 >= 0，当前值: {self.threshold_buffer}")


# ══════════════════════════════════════════════
# CLI 默认值
# ══════════════════════════════════════════════

@dataclass
class CliDefaults:
    """
    main.py CLI 参数的默认值。
    修改此处即可改变 `python main.py` 的默认行为，无需每次传参。
    """
    topic:          str = "AI"
    hotspot_count:  int = 5
    article_style:  str = "深度分析"
    word_count:     int = 1000
    max_revisions:  int = 2
    pass_threshold: int = 85
    output_file:    str = "output.json"

    def __post_init__(self):
        if self.hotspot_count <= 0:
            raise ValueError(f"hotspot_count 必须大于 0，当前值: {self.hotspot_count}")
        if self.word_count <= 0:
            raise ValueError(f"word_count 必须大于 0，当前值: {self.word_count}")
        if not (1 <= self.pass_threshold <= 100):
            raise ValueError(f"pass_threshold 必须在 1-100 范围内，当前值: {self.pass_threshold}")


# ══════════════════════════════════════════════
# 审校配置
# ══════════════════════════════════════════════

@dataclass
class ReviewConfig:
    """
    ReviewerAgent 的评分标准和维度权重。

    核心思路：关键阈值显式声明为配置，而非隐藏在 system prompt 字符串里，
    支持通过 CLI --pass-threshold 快速调整并对比效果。
    """

    pass_threshold: int = CliDefaults.pass_threshold
    """文章通过审校的最低分数（满分 100）。"""

    dimension_weights: Dict[str, int] = field(
        default_factory=lambda: {
            "content_insight":   30,  # 内容洞察（观点独到、有信息增量、非纯资讯搬运）
            "readability":       25,  # 可读性（口语化、短段落、节奏感、移动端友好）
            "title_appeal":      20,  # 标题吸引力（好奇心、传播欲、不低质标题党）
            "structure_flow":    15,  # 结构流畅（钩子开篇、层层递进、结尾有力）
            "accuracy":          10,  # 事实准确性（数据有据可查、因果合理）
        }
    )
    """各维度的满分分值，合计应为 100。"""

    def __post_init__(self):
        if not (1 <= self.pass_threshold <= 100):
            raise ValueError(f"pass_threshold 必须在 1-100 范围内，当前值: {self.pass_threshold}")
        total = sum(self.dimension_weights.values())
        if total != 100:
            raise ValueError(f"dimension_weights 各项之和必须为 100，当前值: {total}")

    def total_score(self) -> int:
        return sum(self.dimension_weights.values())

    def score_description(self) -> str:
        """生成供 system prompt 使用的评分标准文本。"""
        workflow_cfg = WorkflowConfig()
        below = self.pass_threshold - workflow_cfg.threshold_buffer
        return "\n".join([
            f"- {self.pass_threshold}分以上：通过，可以发表",
            f"- {below}-{self.pass_threshold - 1}分：需要小幅修改",
            f"- {below}分以下：需要大幅修改",
        ])

    def dimension_prompt(self) -> str:
        """生成供 system prompt 使用的维度说明文本。"""
        labels = {
            "content_insight": "内容洞察（观点独到、有信息增量、非纯资讯搬运）",
            "readability":     "可读性（口语化、短段落、节奏感、移动端友好）",
            "title_appeal":    "标题吸引力（激发好奇、传播欲强、不用低质词汇）",
            "structure_flow":  "结构流畅（钩子开篇、层层递进、结尾有力）",
            "accuracy":        "事实准确性（数据有据可查、因果关系合理）",
        }
        parts = []
        for i, (key, score) in enumerate(self.dimension_weights.items(), 1):
            label = labels.get(key, key)
            parts.append(f"{i}. **{label}** ({score}分)")
        return "\n".join(parts)
