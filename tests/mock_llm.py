"""
tests/mock_llm.py — 测试专用 MockLLMClient

从 main.py 中独立出来，仅供测试使用。
"""
from __future__ import annotations

import json
from base_agent import LLMClient


class MockLLMClient(LLMClient):
    """
    模拟 LLM 返回，用于单元测试。
    无需任何 API Key，直接返回预设数据。
    """

    def __init__(self):
        super().__init__(api_key="mock", base_url="http://mock", model="mock", api_style="openai")
        self._call_count = 0

    def chat(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return json.dumps(self.chat_json(system_prompt, user_prompt, **kwargs), ensure_ascii=False)

    def chat_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        self._call_count += 1

        if "热点分析师" in system_prompt or "筛选" in system_prompt:
            return self._mock_research()
        elif "评估审校反馈" in system_prompt:
            return self._mock_evaluate_feedback()
        elif "修改文章" in system_prompt:
            return self._mock_revised_article()
        elif "专栏作家" in system_prompt:
            return self._mock_article()
        elif "审校" in system_prompt:
            return self._mock_review()
        else:
            return {"text": "mock response"}

    def _mock_research(self) -> dict:
        return {
            "hotspots": [
                {"title": "Claude Opus 4.6 发布", "summary": "推理能力大幅飞跃", "source": "Anthropic Blog", "relevance_score": 9},
                {"title": "OpenAI 收购 Astral", "summary": "整合至 Codex 产品", "source": "TechCrunch", "relevance_score": 8},
                {"title": "Cursor 发布 Composer 2", "summary": "价格仅为 Claude 的 1/7", "source": "Cursor Blog", "relevance_score": 9},
                {"title": "宇树科技机器人百米破 10 秒", "summary": "中国机器人公司新纪录", "source": "36氪", "relevance_score": 7},
                {"title": "GPT-5.4 Tool Search 发布", "summary": "动态工具检索新范式", "source": "OpenAI Blog", "relevance_score": 8},
            ],
            "selected": {
                "title": "Cursor 发布 Composer 2",
                "reason": "AI 编程领域里程碑事件，话题性强",
            },
        }

    def _mock_article(self) -> dict:
        return {
            "title": "AI 编程的分水岭：当 Cursor 决定自己造模型",
            "content": "## 引言\n\n2026 年 3 月，AI 编程赛道迎来了一个标志性时刻。",
            "word_count": 620,
        }

    def _mock_evaluate_feedback(self) -> dict:
        return {"should_revise": True, "reason": "反馈包含具体可操作的改进建议"}

    def _mock_review(self) -> dict:
        if self._call_count <= 4:
            return {
                "approved": False,
                "overall_score": 78,
                "scores": {"content_quality": 23, "structure": 17, "language": 16, "title_quality": 12, "practical_value": 10},
                "feedback": "1. 缺少具体数据；\n2. 展望部分空泛；\n3. 建议增加用户反馈。",
                "highlights": ["类比恰当", "结构清晰"],
            }
        else:
            return {
                "approved": True,
                "overall_score": 88,
                "scores": {"content_quality": 27, "structure": 18, "language": 18, "title_quality": 13, "practical_value": 12},
                "feedback": "",
                "highlights": ["数据充实", "更接地气", "展望具体"],
            }

    def _mock_revised_article(self) -> dict:
        return {
            "title": "AI 编程的分水岭：当 Cursor 决定自己造模型",
            "content": "## 引言\n\n2026 年 3 月，Cursor 发布了 Composer 2，性能对标 Claude Opus 4.6，价格低 86%。",
            "word_count": 680,
        }
