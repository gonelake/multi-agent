"""
test_orchestrator.py — 编排器单元测试

覆盖：
- Orchestrator 初始化（智能体实例化、参数赋值）
- run() 完整主路径（使用 MockLLMClient）
- 错误路径（Researcher/Writer/Reviewer 各自失败时的降级行为）
- 审校循环边界（max_revisions、approved=True 提前退出）
- WorkflowResult 数据结构
"""
import pytest
from unittest.mock import MagicMock, patch

from base_agent import AgentMessage, MessageType
from agents import ResearcherAgent, WriterAgent, ReviewerAgent
from orchestrator import Orchestrator, WorkflowResult
from mock_llm import MockLLMClient


# ══════════════════════════════════════════════
# Orchestrator 初始化
# ══════════════════════════════════════════════

class TestOrchestratorInit:
    def test_agents_are_instantiated(self):
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, verbose=False)
        assert isinstance(orch.researcher, ResearcherAgent)
        assert isinstance(orch.writer, WriterAgent)
        assert isinstance(orch.reviewer, ReviewerAgent)

    def test_max_revisions_stored(self):
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=3, verbose=False)
        assert orch.max_revisions == 3


# ══════════════════════════════════════════════
# run() 主路径（使用 MockLLMClient）
# ══════════════════════════════════════════════

class TestOrchestratorRunHappyPath:
    """
    MockLLMClient 行为：
    - 热点抓取 → 5 条热点
    - 初稿 → 文章
    - 第1次审校(_call_count<=4) → 78分，不通过
    - 修改 → 修改后文章
    - 第2次审校(_call_count>4) → 88分，通过
    """

    @pytest.fixture
    def result(self):
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=2, verbose=False)
        return orch.run(topic="AI", hotspot_count=5)

    def test_success_is_true(self, result):
        assert result.success is True

    def test_hotspots_not_empty(self, result):
        assert len(result.hotspots) == 5

    def test_selected_topic_has_title(self, result):
        assert "title" in result.selected_topic
        assert len(result.selected_topic["title"]) > 0

    def test_final_article_has_title_and_content(self, result):
        assert "title" in result.final_article
        assert "content" in result.final_article
        assert len(result.final_article["content"]) > 0

    def test_review_history_recorded(self, result):
        # 1 轮修改 → 2 次审校记录
        assert len(result.review_history) == 2

    def test_total_revisions_is_one(self, result):
        assert result.total_revisions == 1

    def test_final_review_approved(self, result):
        last_review = result.review_history[-1]
        assert last_review["approved"] is True
        assert last_review["score"] == 88

    def test_total_time_is_nonnegative(self, result):
        assert result.total_time >= 0.0


# ══════════════════════════════════════════════
# 错误路径
# ══════════════════════════════════════════════

class TestOrchestratorErrorPaths:
    def _make_error_agent_msg(self, error_text="模拟错误"):
        return AgentMessage(
            sender="agent",
            receiver="orchestrator",
            msg_type=MessageType.ERROR,
            payload={"error": error_text},
        )

    def test_researcher_error_returns_failure(self):
        """ResearcherAgent 返回 ERROR → WorkflowResult.success=False"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, verbose=False)

        with patch.object(orch.researcher, "run", return_value=self._make_error_agent_msg()):
            result = orch.run()

        assert result.success is False
        assert result.hotspots == []
        assert result.final_article == {}

    def test_writer_error_returns_failure(self):
        """WriterAgent 返回 ERROR → WorkflowResult.success=False"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, verbose=False)

        with patch.object(orch.writer, "run", return_value=self._make_error_agent_msg()):
            result = orch.run()

        assert result.success is False
        assert result.final_article == {}

    def test_reviewer_error_breaks_loop(self):
        """ReviewerAgent 返回 ERROR → 循环中断，但 success=True（使用已有文章）"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, verbose=False)

        with patch.object(orch.reviewer, "run", return_value=self._make_error_agent_msg()):
            result = orch.run()

        # 审校失败时循环 break，使用当前文章，success=True（流程已完成写作）
        assert result.final_article != {}
        assert result.review_history == []  # 审校失败时无历史记录


# ══════════════════════════════════════════════
# 审校循环边界
# ══════════════════════════════════════════════

class TestOrchestratorReviewLoop:
    def test_approved_on_first_review_no_revision(self):
        """首次审校就通过 → total_revisions=0，review_history 只有 1 条"""
        llm = MockLLMClient()
        # 强制 _call_count 足够大，让 mock 直接返回 approved=True
        llm._call_count = 100
        orch = Orchestrator(llm=llm, max_revisions=2, verbose=False)
        result = orch.run()

        assert result.review_history[-1]["approved"] is True
        # 当首次审校即通过，total_revisions 应为 0（未发生修改）
        assert result.total_revisions == 0

    def test_max_revisions_zero_runs_review_once(self):
        """max_revisions=0 时：写一次初稿，审校一次，无论通过与否就结束"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=0, verbose=False)
        result = orch.run()

        # 只有一次审校记录（不通过但已达上限）
        assert len(result.review_history) == 1

    def test_review_history_records_scores_per_round(self):
        """每轮审校都记录了 score, approved, feedback, highlights"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=2, verbose=False)
        result = orch.run()

        for record in result.review_history:
            assert "score" in record
            assert "approved" in record
            assert "revision" in record

    def test_max_revisions_limits_writer_calls(self):
        """Writer 最多被调用 max_revisions+1 次（1次初稿 + max_revisions次修改）"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=1, verbose=False)

        call_count = {"n": 0}
        original_writer_run = orch.writer.run

        def counting_run(msg):
            call_count["n"] += 1
            return original_writer_run(msg)

        with patch.object(orch.writer, "run", side_effect=counting_run):
            orch.run()

        # max_revisions=1: 最多 1 次初稿 + 1 次修改 = 2 次
        assert call_count["n"] <= 2


# ══════════════════════════════════════════════
# WorkflowResult 数据结构
# ══════════════════════════════════════════════

class TestWorkflowResult:
    def test_success_result_fields(self):
        r = WorkflowResult(
            success=True,
            hotspots=[{"title": "h"}],
            selected_topic={"title": "s"},
            final_article={"title": "a", "content": "c"},
            review_history=[{"revision": 0, "score": 88}],
            total_revisions=1,
            total_time=5.5,
        )
        assert r.success is True
        assert len(r.hotspots) == 1
        assert r.total_revisions == 1
        assert r.total_time == 5.5

    def test_failure_result_fields(self):
        r = WorkflowResult(
            success=False,
            hotspots=[],
            selected_topic={},
            final_article={},
            review_history=[],
            total_revisions=0,
            total_time=0.1,
        )
        assert r.success is False
        assert r.hotspots == []
        assert r.final_article == {}


# ══════════════════════════════════════════════
# Writer 自主决策 — Orchestrator 跳过逻辑
# ══════════════════════════════════════════════

class TestOrchestratorWriterRejection:
    """验证 Writer 拒绝反馈时，Orchestrator 的跳过行为"""

    def _make_rejection_response(self, current_article: dict) -> AgentMessage:
        """构造 Writer 拒绝反馈时的返回消息"""
        return AgentMessage(
            sender="writer",
            receiver="orchestrator",
            msg_type=MessageType.RESULT,
            payload={
                "title": current_article.get("title", "原文标题"),
                "content": current_article.get("content", "原文内容"),
                "word_count": len(current_article.get("content", "")),
                "revision": 1,
                "feedback_accepted": False,
                "rejection_reason": "反馈过于模糊",
            },
        )

    def test_writer_rejection_preserves_current_article(self):
        """Writer 拒绝反馈时，final_article 保持拒绝前的版本"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=2, verbose=False)

        # 伪造一篇"已有文章"
        original_article = {"title": "原文标题", "content": "原文内容", "word_count": 4}

        with patch.object(
            orch.writer, "run",
            side_effect=lambda msg: (
                # 初稿调用：返回原文
                AgentMessage("writer", "orchestrator", MessageType.RESULT, original_article)
                if not msg.payload.get("feedback")
                # 修改调用：拒绝反馈
                else self._make_rejection_response(original_article)
            ),
        ):
            result = orch.run()

        assert result.final_article.get("content") == "原文内容"

    def test_writer_rejection_does_not_consume_revision_quota(self):
        """Writer 拒绝时 revision_count 回退，不消耗修改配额"""
        llm = MockLLMClient()
        orch = Orchestrator(llm=llm, max_revisions=1, verbose=False)

        original_article = {"title": "T", "content": "C", "word_count": 1}
        rejection_result = AgentMessage(
            "writer", "orchestrator", MessageType.RESULT,
            {"title": "T", "content": "C", "word_count": 1,
             "revision": 1, "feedback_accepted": False, "rejection_reason": "模糊"},
        )

        call_count = {"n": 0}

        def writer_run(msg):
            call_count["n"] += 1
            if msg.payload.get("feedback"):
                return rejection_result
            return AgentMessage("writer", "orchestrator", MessageType.RESULT, original_article)

        with patch.object(orch.writer, "run", side_effect=writer_run):
            result = orch.run()

        # 拒绝后 revision_count 回退，total_revisions 不应把被拒绝的轮次计入
        assert result.total_revisions == 0
