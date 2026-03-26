"""
test_experiments.py — ExperimentLog & ExperimentTracker 单元测试

覆盖：
- ExperimentLog 构造和 from_workflow_result 工厂方法
- ExperimentTracker.log 写入 TSV
- ExperimentTracker.read_all 读取记录
- ExperimentTracker.summary 统计摘要
- header 自动创建
- 多次追加
"""
import os
import pytest
import tempfile

from experiments import ExperimentLog, ExperimentTracker
from orchestrator import WorkflowResult


# ══════════════════════════════════════════════
# 辅助工厂
# ══════════════════════════════════════════════

def make_log(
    topic="AI",
    final_score=88.0,
    revisions=1,
    status="pass",
    description="test",
    pass_threshold=85,
) -> ExperimentLog:
    return ExperimentLog(
        timestamp="2026-03-26T14:30:00",
        topic=topic,
        word_count=1000,
        final_score=final_score,
        revisions=revisions,
        status=status,
        description=description,
        execution_time=12.5,
        pass_threshold=pass_threshold,
    )


def make_workflow_result(score=88, approved=True, revisions=1, success=True) -> WorkflowResult:
    return WorkflowResult(
        success=success,
        hotspots=[],
        selected_topic={},
        final_article={"title": "T", "content": "C"},
        review_history=[{"revision": 0, "score": score, "approved": approved}],
        total_revisions=revisions,
        total_time=12.5,
    )


# ══════════════════════════════════════════════
# ExperimentLog
# ══════════════════════════════════════════════

class TestExperimentLog:
    def test_basic_fields(self):
        log = make_log()
        assert log.topic == "AI"
        assert log.final_score == 88.0
        assert log.status == "pass"

    def test_from_workflow_result_pass(self):
        result = make_workflow_result(score=88, approved=True)
        log = ExperimentLog.from_workflow_result(
            result=result,
            topic="AI",
            word_count=1000,
            description="test",
            execution_time=5.0,
            pass_threshold=85,
        )
        assert log.status == "pass"
        assert log.final_score == 88.0
        assert log.revisions == 1
        assert log.pass_threshold == 85

    def test_from_workflow_result_fail_not_approved(self):
        """审校未通过 → status=fail"""
        result = make_workflow_result(score=78, approved=False)
        log = ExperimentLog.from_workflow_result(
            result=result, topic="AI", word_count=1000,
            description="test", execution_time=5.0, pass_threshold=85,
        )
        assert log.status == "fail"

    def test_from_workflow_result_no_review_history(self):
        """无审校历史 → score=0, status=fail"""
        result = WorkflowResult(
            success=False, hotspots=[], selected_topic={},
            final_article={}, review_history=[], total_revisions=0, total_time=1.0,
        )
        log = ExperimentLog.from_workflow_result(
            result=result, topic="AI", word_count=1000,
            description="test", execution_time=1.0, pass_threshold=85,
        )
        assert log.final_score == 0.0
        assert log.status == "fail"

    def test_timestamp_format(self):
        result = make_workflow_result()
        log = ExperimentLog.from_workflow_result(
            result=result, topic="AI", word_count=1000,
            description="test", execution_time=1.0,
        )
        # 应为 ISO 格式 YYYY-MM-DDTHH:MM:SS
        assert "T" in log.timestamp
        assert len(log.timestamp) == 19


# ══════════════════════════════════════════════
# ExperimentTracker
# ══════════════════════════════════════════════

class TestExperimentTracker:
    @pytest.fixture
    def tsv_path(self, tmp_path):
        """每个测试使用独立的临时 TSV 文件"""
        return str(tmp_path / "test_experiments.tsv")

    def test_creates_file_with_header_on_init(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        assert os.path.exists(tsv_path)
        with open(tsv_path) as f:
            header = f.readline().strip()
        assert "timestamp" in header
        assert "final_score" in header
        assert "pass_threshold" in header

    def test_log_appends_row(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        tracker.log(make_log())
        rows = tracker.read_all()
        assert len(rows) == 1
        assert rows[0]["topic"] == "AI"
        assert rows[0]["status"] == "pass"

    def test_log_multiple_rows(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        tracker.log(make_log(description="exp1"))
        tracker.log(make_log(description="exp2", status="fail", final_score=72.0))
        tracker.log(make_log(description="exp3"))
        rows = tracker.read_all()
        assert len(rows) == 3
        assert rows[1]["status"] == "fail"

    def test_pass_threshold_stored_in_tsv(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        tracker.log(make_log(pass_threshold=90))
        rows = tracker.read_all()
        assert rows[0]["pass_threshold"] == "90"

    def test_read_all_empty_file(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        assert tracker.read_all() == []

    def test_summary_returns_none_when_empty(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        assert tracker.summary() is None

    def test_summary_stats(self, tsv_path):
        tracker = ExperimentTracker(tsv_path)
        tracker.log(make_log(final_score=88.0, status="pass"))
        tracker.log(make_log(final_score=72.0, status="fail"))
        summary = tracker.summary()
        assert summary is not None
        assert "2" in summary       # 总数
        assert "50.0%" in summary   # 通过率 1/2

    def test_no_duplicate_header_on_existing_file(self, tsv_path):
        """文件已存在时不应重写 header"""
        tracker = ExperimentTracker(tsv_path)
        tracker.log(make_log())
        # 再次初始化同一文件
        tracker2 = ExperimentTracker(tsv_path)
        tracker2.log(make_log())
        rows = tracker2.read_all()
        assert len(rows) == 2  # 应有 2 条记录，不是 1 条 + 重复 header
