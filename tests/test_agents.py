"""
test_agents.py — 三个业务智能体单元测试

覆盖：
- ResearcherAgent.process（正常路径、默认参数、消息格式）
- WriterAgent.process（初稿模式、修改模式、revision 回写）
- ReviewerAgent.process（通过路径、未通过路径、scores 结构）
"""
import pytest
from unittest.mock import MagicMock

from base_agent import AgentMessage, MessageType
from agents import ResearcherAgent, WriterAgent, ReviewerAgent
from config import ReviewConfig
from search import DuckDuckGoSearchClient


# ══════════════════════════════════════════════
# 共用工具函数
# ══════════════════════════════════════════════

def make_task(payload: dict) -> AgentMessage:
    return AgentMessage(
        sender="orchestrator",
        receiver="agent",
        msg_type=MessageType.TASK,
        payload=payload,
    )


def make_mock_llm(json_response: dict) -> MagicMock:
    """返回固定 JSON 的 mock LLM"""
    llm = MagicMock()
    llm.chat_json.return_value = json_response
    return llm


# ══════════════════════════════════════════════
# ResearcherAgent
# ══════════════════════════════════════════════

class TestResearcherAgent:
    MOCK_RESULT = {
        "hotspots": [
            {"title": "热点A", "summary": "摘要A", "source": "来源A", "relevance_score": 9},
            {"title": "热点B", "summary": "摘要B", "source": "来源B", "relevance_score": 7},
        ],
        "selected": {"title": "热点A", "reason": "最相关"},
    }

    def test_normal_flow_returns_result_message(self):
        agent = ResearcherAgent("Researcher", make_mock_llm(self.MOCK_RESULT), verbose=False)
        msg = make_task({"topic": "AI", "count": 2})
        result = agent.run(msg)

        assert result.msg_type is MessageType.RESULT
        assert "hotspots" in result.payload
        assert "selected" in result.payload

    def test_hotspots_list_content(self):
        agent = ResearcherAgent("Researcher", make_mock_llm(self.MOCK_RESULT), verbose=False)
        result = agent.run(make_task({"topic": "AI", "count": 2}))

        hotspots = result.payload["hotspots"]
        assert len(hotspots) == 2
        assert hotspots[0]["title"] == "热点A"
        assert hotspots[0]["relevance_score"] == 9

    def test_sender_and_receiver_in_result(self):
        agent = ResearcherAgent("Researcher", make_mock_llm(self.MOCK_RESULT), verbose=False)
        result = agent.run(make_task({"topic": "科技", "count": 5}))

        assert result.sender == "Researcher"
        assert result.receiver == "orchestrator"

    def test_llm_exception_returns_error_message(self):
        llm = MagicMock()
        llm.chat_json.side_effect = Exception("API 超时")
        agent = ResearcherAgent("Researcher", llm, verbose=False)
        result = agent.run(make_task({"topic": "AI", "count": 5}))

        assert result.msg_type is MessageType.ERROR
        assert "API 超时" in result.payload["error"]

    def test_with_tavily_search_client_uses_real_results(self):
        """有 DuckDuckGoSearchClient 时，用真实搜索结果，LLM 用较低 temperature 分析。"""
        mock_search = MagicMock(spec=DuckDuckGoSearchClient)
        mock_search.search_multi.return_value = [
            {
                "title": "GPT-5 发布",
                "url": "https://example.com/1",
                "content": "OpenAI 发布 GPT-5，性能大幅提升。",
                "published_date": "2026-03-25",
                "score": 0.95,
            },
            {
                "title": "Claude 4 上线",
                "url": "https://example.com/2",
                "content": "Anthropic 发布 Claude 4 模型。",
                "published_date": "2026-03-24",
                "score": 0.90,
            },
        ]

        agent = ResearcherAgent(
            "Researcher",
            make_mock_llm(self.MOCK_RESULT),
            search_client=mock_search,
            verbose=False,
        )
        result = agent.run(make_task({"topic": "AI", "count": 2}))

        # 确认调用了 Tavily 搜索
        mock_search.search_multi.assert_called_once()
        # 结果仍符合标准格式
        assert result.msg_type is MessageType.RESULT
        assert "hotspots" in result.payload

    def test_with_tavily_empty_results_falls_back_to_llm(self):
        """搜索返回空结果时，降级到 LLM 生成。"""
        mock_search = MagicMock(spec=DuckDuckGoSearchClient)
        mock_search.search_multi.return_value = []  # 空结果

        agent = ResearcherAgent(
            "Researcher",
            make_mock_llm(self.MOCK_RESULT),
            search_client=mock_search,
            verbose=False,
        )
        result = agent.run(make_task({"topic": "AI", "count": 2}))

        # 仍应成功（降级到 LLM 模式）
        assert result.msg_type is MessageType.RESULT
        assert "hotspots" in result.payload


# ══════════════════════════════════════════════
# WriterAgent
# ══════════════════════════════════════════════

class TestWriterAgent:
    MOCK_ARTICLE = {
        "title": "AI 的未来",
        "content": "## 引言\n文章内容...",
        "word_count": 500,
    }

    MOCK_REVISED = {
        "title": "AI 的未来（修改版）",
        "content": "## 引言\n修改后的内容...",
        "word_count": 600,
    }

    def test_draft_mode_no_feedback(self):
        """无 feedback 时走初稿路径"""
        agent = WriterAgent("Writer", make_mock_llm(self.MOCK_ARTICLE), verbose=False)
        msg = make_task({
            "topic": {"title": "AI 的未来", "summary": "...", "reason": "..."},
            "style": "深度分析",
            "word_count": 500,
            "revision": 0,
        })
        result = agent.run(msg)

        assert result.msg_type is MessageType.RESULT
        assert result.payload["title"] == "AI 的未来"
        assert "content" in result.payload

    def test_draft_mode_revision_field_is_zero(self):
        agent = WriterAgent("Writer", make_mock_llm(self.MOCK_ARTICLE), verbose=False)
        msg = make_task({
            "topic": {"title": "话题"},
            "style": "深度分析",
            "word_count": 500,
            "revision": 0,
        })
        result = agent.run(msg)
        assert result.payload["revision"] == 0

    def test_revise_mode_with_feedback(self):
        """有 feedback 时走修改路径，使用 REVISE_PROMPT"""
        llm = make_mock_llm(self.MOCK_REVISED)
        agent = WriterAgent("Writer", llm, verbose=False)
        msg = make_task({
            "topic": {"title": "话题"},
            "style": "深度分析",
            "word_count": 600,
            "revision": 1,
            "feedback": "请增加更多数据",
            "original_article": "原始文章内容",
        })
        result = agent.run(msg)

        assert result.msg_type is MessageType.RESULT
        assert result.payload["revision"] == 1
        # 修改模式现在先评估（1次）再修改（1次），共 2 次
        assert llm.chat_json.call_count == 2

    def test_revise_mode_uses_revise_prompt(self):
        """修改模式的 system_prompt 包含 '修改文章' 关键字"""
        llm = make_mock_llm(self.MOCK_REVISED)
        agent = WriterAgent("Writer", llm, verbose=False)
        msg = make_task({
            "topic": {"title": "话题"},
            "style": "深度分析",
            "word_count": 600,
            "revision": 1,
            "feedback": "意见",
            "original_article": "原文",
        })
        agent.run(msg)

        call_kwargs = llm.chat_json.call_args
        system_prompt = call_kwargs[1].get("system_prompt") or call_kwargs[0][0]
        assert "修改文章" in system_prompt

    def test_llm_exception_returns_error_message(self):
        llm = MagicMock()
        llm.chat_json.side_effect = RuntimeError("模型错误")
        agent = WriterAgent("Writer", llm, verbose=False)
        result = agent.run(make_task({
            "topic": {"title": "话题"},
            "style": "深度分析",
            "word_count": 500,
            "revision": 0,
        }))
        assert result.msg_type is MessageType.ERROR


# ══════════════════════════════════════════════
# ReviewerAgent
# ══════════════════════════════════════════════

class TestReviewerAgent:
    MOCK_APPROVED = {
        "approved": True,
        "overall_score": 88,
        "scores": {
            "content_quality": 27,
            "structure": 18,
            "language": 18,
            "title_quality": 13,
            "practical_value": 12,
        },
        "feedback": "",
        "highlights": ["文章结构清晰", "数据充分"],
    }

    MOCK_REJECTED = {
        "approved": False,
        "overall_score": 72,
        "scores": {
            "content_quality": 20,
            "structure": 15,
            "language": 15,
            "title_quality": 12,
            "practical_value": 10,
        },
        "feedback": "1. 缺少数据；2. 结论不够明确",
        "highlights": ["标题吸引人"],
    }

    def test_approved_path(self):
        """88 分 >= 默认阈值 85 → approved=True"""
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_APPROVED), verbose=False)
        msg = make_task({"title": "文章标题", "content": "文章内容", "revision": 0})
        result = agent.run(msg)

        assert result.msg_type is MessageType.RESULT
        assert result.payload["approved"] is True
        assert result.payload["overall_score"] == 88

    def test_rejected_path_has_feedback(self):
        """72 分 < 默认阈值 85 → approved=False"""
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_REJECTED), verbose=False)
        msg = make_task({"title": "文章标题", "content": "内容", "revision": 0})
        result = agent.run(msg)

        assert result.payload["approved"] is False
        assert len(result.payload["feedback"]) > 0

    def test_scores_dict_has_five_dimensions(self):
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_APPROVED), verbose=False)
        result = agent.run(make_task({"title": "T", "content": "C", "revision": 0}))

        scores = result.payload["scores"]
        expected_keys = {"content_quality", "structure", "language", "title_quality", "practical_value"}
        assert set(scores.keys()) == expected_keys

    def test_highlights_list_returned(self):
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_APPROVED), verbose=False)
        result = agent.run(make_task({"title": "T", "content": "C", "revision": 1}))
        assert isinstance(result.payload["highlights"], list)
        assert len(result.payload["highlights"]) > 0

    def test_custom_threshold_88_rejects_score_88(self):
        """阈值 89 时，88 分 < 89 → approved=False（严格模式）"""
        config = ReviewConfig(pass_threshold=89)
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_APPROVED), config=config, verbose=False)
        result = agent.run(make_task({"title": "T", "content": "C", "revision": 0}))
        assert result.payload["approved"] is False

    def test_custom_threshold_70_approves_score_72(self):
        """阈值 70 时，72 分 >= 70 → approved=True（宽松模式）"""
        config = ReviewConfig(pass_threshold=70)
        agent = ReviewerAgent("Reviewer", make_mock_llm(self.MOCK_REJECTED), config=config, verbose=False)
        result = agent.run(make_task({"title": "T", "content": "C", "revision": 0}))
        assert result.payload["approved"] is True

    def test_reviewer_uses_config_threshold_not_llm_approved(self):
        """approved 字段完全由 config.pass_threshold 决定，不受 LLM 返回的 approved 影响"""
        # LLM 返回 approved=True，但分数 72 < 阈值 80
        mock_result = {**self.MOCK_REJECTED, "overall_score": 72, "approved": True}
        config = ReviewConfig(pass_threshold=80)
        agent = ReviewerAgent("Reviewer", make_mock_llm(mock_result), config=config, verbose=False)
        result = agent.run(make_task({"title": "T", "content": "C", "revision": 0}))
        # 应以 config 为准：72 < 80 → False
        assert result.payload["approved"] is False


# ══════════════════════════════════════════════
# WriterAgent — 自主决策（借鉴点 3）
# ══════════════════════════════════════════════

def make_writer_with_responses(*responses):
    """构造一个按顺序返回不同 JSON 的 mock LLM WriterAgent"""
    llm = MagicMock()
    llm.chat_json.side_effect = list(responses)
    return WriterAgent("Writer", llm, verbose=False)


MOCK_REVISED_ARTICLE = {
    "title": "改后标题",
    "content": "改后内容",
    "word_count": 500,
}

FEEDBACK_PAYLOAD = {
    "topic": {"title": "话题"},
    "style": "深度分析",
    "word_count": 500,
    "revision": 1,
    "feedback": "1. 补充具体数据；2. 增加开发者案例反馈。",
    "original_title": "原文标题",
    "original_article": "原文内容",
}


class TestWriterAgentFeedbackEvaluation:

    def test_accepts_valuable_feedback_and_revises(self):
        """LLM 判断 should_revise=True → 正常进入修改流程"""
        eval_response = {"should_revise": True, "reason": "反馈包含具体可操作建议"}
        revise_response = MOCK_REVISED_ARTICLE
        agent = make_writer_with_responses(eval_response, revise_response)

        result = agent.run(make_task(FEEDBACK_PAYLOAD))

        assert result.msg_type is MessageType.RESULT
        assert result.payload.get("feedback_accepted") is True
        assert result.payload["title"] == "改后标题"

    def test_rejects_low_value_feedback_returns_original(self):
        """LLM 判断 should_revise=False → 返回原文，feedback_accepted=False"""
        eval_response = {"should_revise": False, "reason": "反馈过于模糊"}
        agent = make_writer_with_responses(eval_response)

        result = agent.run(make_task(FEEDBACK_PAYLOAD))

        assert result.msg_type is MessageType.RESULT
        assert result.payload.get("feedback_accepted") is False
        assert result.payload["content"] == "原文内容"
        assert result.payload["title"] == "原文标题"

    def test_rejection_payload_contains_reason(self):
        """拒绝时 payload 包含非空 rejection_reason"""
        eval_response = {"should_revise": False, "reason": "仅涉及格式小问题"}
        agent = make_writer_with_responses(eval_response)

        result = agent.run(make_task(FEEDBACK_PAYLOAD))

        assert result.payload.get("rejection_reason") == "仅涉及格式小问题"

    def test_evaluate_called_with_low_temperature(self):
        """评估调用使用 temperature=0.1"""
        llm = MagicMock()
        # 第一次（评估）返回接受，第二次（修改）返回文章
        llm.chat_json.side_effect = [
            {"should_revise": True, "reason": "ok"},
            MOCK_REVISED_ARTICLE,
        ]
        agent = WriterAgent("Writer", llm, verbose=False)
        agent.run(make_task(FEEDBACK_PAYLOAD))

        # 评估是第一次 chat_json 调用
        first_call_kwargs = llm.chat_json.call_args_list[0]
        temperature = first_call_kwargs[1].get("temperature") or first_call_kwargs[0][2] if len(first_call_kwargs[0]) > 2 else first_call_kwargs[1].get("temperature")
        assert temperature == 0.1

    def test_no_evaluation_on_initial_draft(self):
        """初稿模式（无 feedback）不触发评估，chat_json 只调用一次"""
        llm = MagicMock()
        llm.chat_json.return_value = {"title": "T", "content": "C", "word_count": 100}
        agent = WriterAgent("Writer", llm, verbose=False)
        agent.run(make_task({
            "topic": {"title": "话题", "summary": "", "reason": ""},
            "style": "深度分析",
            "word_count": 500,
            "revision": 0,
        }))
        assert llm.chat_json.call_count == 1

    def test_evaluation_failure_falls_back_to_accept(self):
        """评估调用抛异常时，保守地接受反馈（不中断流程）"""
        llm = MagicMock()
        # 第一次（评估）抛异常，第二次（修改）正常返回
        llm.chat_json.side_effect = [Exception("评估超时"), MOCK_REVISED_ARTICLE]
        agent = WriterAgent("Writer", llm, verbose=False)

        result = agent.run(make_task(FEEDBACK_PAYLOAD))

        # 评估失败后应保守接受，继续修改
        assert result.msg_type is MessageType.RESULT
        assert result.payload.get("feedback_accepted") is True
