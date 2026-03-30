---
name: multi-agent-writer
description: Use when you need to generate a high-quality AI news article — fetches real-time hotspots via DuckDuckGo, writes a WeChat-style article, and iterates through an automated review-revision cycle. Triggers include requests for "写文章", "生成新闻", "热点文章", "AI新闻", or any article generation task for a given topic/domain.
allowed-tools: Bash,Read
---

# Multi-Agent Writer

## 概述

一个三阶段多智能体写作流水线：
1. **热点抓取** — DuckDuckGo 搜索近7天实时新闻，LLM 筛选推荐选题
2. **文章撰写** — WriterAgent 生成微信公众号风格文章（含3组备选标题）
3. **审校循环** — ReviewerAgent 按5维度打分，低于通过线则自动触发修改，最多 N 轮

**系统位置：** `/Users/landwei/Documents/AI/multi-agent/`

---

## 快速调用

### Demo 模式（无需 API Key，约1秒完成）

```bash
cd /Users/landwei/Documents/AI/multi-agent
python main.py --demo
python main.py --demo --topic "量子计算" --words 800
```

### 生产模式（需要 `.env` 配置 LLM API Key）

```bash
cd /Users/landwei/Documents/AI/multi-agent
python main.py --topic "AI" --words 1000 --pass-threshold 85
```

---

## 全部 CLI 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--topic` | str | `"AI"` | 关注的领域/话题 |
| `--count` | int | `5` | 抓取热点数量 |
| `--style` | str | `"深度分析"` | 文章写作风格 |
| `--words` | int | `1000` | 目标字数 |
| `--max-revisions` | int | `2` | 最大审校-修改轮次 |
| `--pass-threshold` | int | `85` | 审校通过最低分（1-100） |
| `--output` | str | `"output.json"` | 输出文件路径 |
| `--description` | str | `""` | 实验描述（记录到 tsv） |
| `--demo` | flag | `False` | 使用 Mock LLM，无需 API |

---

## 输出文件

| 文件 | 格式 | 内容 |
|------|------|------|
| `output.json` | JSON | 完整结果：热点、文章、审校历史、耗时 |
| `output.md` | Markdown | 可直接复制的文章正文 |
| `experiments.tsv` | TSV | 追加实验记录（分数、状态、通过线等） |

### output.json 结构示例

```json
{
  "hotspots": [...],
  "selected_topic": {"title": "...", "reason": "..."},
  "final_article": {
    "title": "...",
    "content": "...",
    "word_count": 620,
    "revision": 1
  },
  "review_history": [
    {"revision": 0, "score": 78, "approved": false, "feedback": "..."},
    {"revision": 1, "score": 88, "approved": true}
  ],
  "total_revisions": 1,
  "total_time_seconds": 15.3
}
```

---

## Python 程序化调用

当你需要在代码中集成本系统时：

```python
import sys
sys.path.insert(0, "/Users/landwei/Documents/AI/multi-agent")

from orchestrator import Orchestrator
from base_agent import LLMClient
from config import ReviewConfig, LLMConfig, LLMClientConfig
from search import DuckDuckGoSearchClient

# 初始化 LLM（从 .env 读取配置）
llm_config = LLMConfig.from_env()
llm = LLMClient(
    api_key=llm_config.api_key,
    base_url=llm_config.base_url,
    model=llm_config.model,
    api_style=llm_config.api_style,
    client_config=LLMClientConfig(),
)

# 配置审校标准
review_config = ReviewConfig(pass_threshold=85)

# 创建协调器
orchestrator = Orchestrator(
    llm=llm,
    max_revisions=2,
    verbose=True,
    review_config=review_config,
    search_client=DuckDuckGoSearchClient(),
)

# 执行工作流
result = orchestrator.run(
    topic="AI",
    hotspot_count=5,
    article_style="深度分析",
    article_word_count=1000,
)

# 获取结果
print(result.final_article["title"])
print(result.final_article["content"])
print(f"最终分数: {result.review_history[-1]['score']}")
```

---

## 审校维度（5维，共100分）

| 维度 | 权重 | 说明 |
|------|------|------|
| 内容洞察力 | 30分 | 新颖观点、信息价值 |
| 可读性 | 25分 | 短段落、移动端友好 |
| 标题吸引力 | 20分 | 点击率、情绪共鸣 |
| 结构流畅性 | 15分 | 开篇钩子、逻辑递进 |
| 准确性 | 10分 | 事实正确 |

---

## 环境配置（`.env` 文件）

```bash
# 必填
LLM_API_KEY=your-api-key

# 可选（有默认值）
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=moonshot-v1-8k
LLM_API_STYLE=openai   # "openai" 或 "anthropic"
```

支持的 LLM：Kimi、DeepSeek、OpenAI、Claude、Qwen、GLM、Ollama 等所有兼容 OpenAI/Anthropic API 的模型。

---

## 常见场景

```bash
# 生成科技领域热点文章
python main.py --topic "AI大模型" --words 1500 --style "深度分析"

# 严格评分 A/B 测试
python main.py --demo --pass-threshold 90 --description "strict_90"
python main.py --demo --pass-threshold 75 --description "loose_75"

# 查看实验历史
cat /Users/landwei/Documents/AI/multi-agent/experiments.tsv

# 运行测试（验证系统完整性）
cd /Users/landwei/Documents/AI/multi-agent && pytest
```

---

## 已知问题与修复记录

### WriterAgent 标题输出为单字母（已修复）

**现象：** 文章修改轮次后，`output.json` 中 `final_article.title` 为 `"C"` 等单字母，最终文章显示为 `# C`。

**根因：** `agents.py` 的 `REVISE_PROMPT` 中 `title` 字段描述歧义（"从A/B/C中选最优的一个"），LLM 将选项字母本身当作标题返回。

**修复内容（`agents.py`）：**
1. Prompt 表述改为"直接复制标题文本，不要只写字母A/B/C"
2. 加防御性解析：title 为单字母时自动从 titles 字典取完整文本

```python
# agents.py:410-413 — 防御性修复
title_val = result.get("title", "")
if len(title_val.strip()) <= 1 and title_val.strip().upper() in result.get("titles", {}):
    result["title"] = result["titles"][title_val.strip().upper()]
```

---

## 关键文件路径

```
/Users/landwei/Documents/AI/multi-agent/
├── main.py           # CLI 入口
├── orchestrator.py   # 工作流协调器（Orchestrator.run()）
├── agents.py         # 3个业务智能体
├── base_agent.py     # LLMClient、BaseAgent 框架
├── config.py         # 所有配置类（ReviewConfig、LLMConfig等）
├── search.py         # DuckDuckGo 搜索封装
├── experiments.py    # 实验追踪（TSV）
├── .env              # API Key（严格模式，缺失则启动报错）
└── tests/
    └── mock_llm.py   # MockLLMClient（demo模式使用）
```
