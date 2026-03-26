"""
experiments.py — 实验追踪模块

仿照 autoresearch 的 results.tsv 设计：
每次运行后将结果追加到 TSV 文件，支持历史对比和数据分析。

用法：
    from experiments import ExperimentTracker, ExperimentLog
    
    tracker = ExperimentTracker("experiments.tsv")
    tracker.log(ExperimentLog(
        timestamp="2026-03-26T14:30:00",
        topic="AI",
        word_count=1000,
        final_score=88.0,
        revisions=1,
        status="pass",
        description="baseline",
        execution_time=12.5,
    ))

分析（pandas）：
    import pandas as pd
    df = pd.read_csv("experiments.tsv", sep="\\t")
    print(df[df["status"] == "pass"]["final_score"].describe())
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ExperimentLog:
    """
    单次实验的结构化记录。
    
    对应 autoresearch 中的 results.tsv 行：
      commit  val_bpb  memory_gb  status  description
    本系统的等价物：
      timestamp  topic  word_count  final_score  revisions  status  description  execution_time
    """
    timestamp: str          # ISO 格式时间戳，如 "2026-03-26T14:30:00"
    topic: str              # 文章主题领域，如 "AI"、"科技"
    word_count: int         # 目标字数
    final_score: float      # 最终审校得分（0-100）
    revisions: int          # 实际修改轮次
    status: str             # "pass"（通过）或 "fail"（未通过/失败）
    description: str        # 实验描述，如 "baseline"、"pass_threshold=90"
    execution_time: float   # 总运行耗时（秒）
    pass_threshold: int = 85  # 本次使用的通过阈值（便于对比不同阈值实验）

    @classmethod
    def from_workflow_result(
        cls,
        result,
        topic: str,
        word_count: int,
        description: str,
        execution_time: float,
        pass_threshold: int = 85,
    ) -> "ExperimentLog":
        """从 WorkflowResult 便捷构造 ExperimentLog。"""
        final_score = (
            result.review_history[-1]["score"]
            if result.review_history
            else 0.0
        )
        status = "pass" if (result.success and result.review_history and
                            result.review_history[-1].get("approved", False)) else "fail"
        return cls(
            timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            topic=topic,
            word_count=word_count,
            final_score=float(final_score),
            revisions=result.total_revisions,
            status=status,
            description=description or "no description",
            execution_time=round(execution_time, 1),
            pass_threshold=pass_threshold,
        )


class ExperimentTracker:
    """
    实验追踪器：将每次运行结果追加到 TSV 文件。
    
    文件格式：
        timestamp  topic  word_count  final_score  revisions  status  description  execution_time  pass_threshold
    
    设计要点（来自 autoresearch）：
    - TSV 而非 JSON：pandas 直接读取，无需解析
    - 只追加：不修改历史记录，保持完整性
    - 简单列名：便于 grep、awk 等工具处理
    """

    COLUMNS = [
        "timestamp",
        "topic",
        "word_count",
        "final_score",
        "revisions",
        "status",
        "description",
        "execution_time",
        "pass_threshold",
    ]

    def __init__(self, tracking_file: str = "experiments.tsv"):
        self.tracking_file = tracking_file
        self._ensure_header()

    def _ensure_header(self) -> None:
        """若文件不存在，写入表头行。"""
        if not os.path.exists(self.tracking_file):
            with open(self.tracking_file, "w", encoding="utf-8") as f:
                f.write("\t".join(self.COLUMNS) + "\n")

    def log(self, entry: ExperimentLog) -> None:
        """将一条实验记录追加到 TSV 文件。"""
        row = "\t".join([
            entry.timestamp,
            entry.topic,
            str(entry.word_count),
            f"{entry.final_score:.1f}",
            str(entry.revisions),
            entry.status,
            entry.description,
            f"{entry.execution_time:.1f}",
            str(entry.pass_threshold),
        ])
        with open(self.tracking_file, "a", encoding="utf-8") as f:
            f.write(row + "\n")

    def read_all(self) -> List[dict]:
        """读取所有实验记录，返回字典列表。"""
        if not os.path.exists(self.tracking_file):
            return []
        rows = []
        with open(self.tracking_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return []
        header = lines[0].strip().split("\t")
        for line in lines[1:]:
            values = line.strip().split("\t")
            if len(values) == len(header):
                rows.append(dict(zip(header, values)))
        return rows

    def summary(self) -> Optional[str]:
        """打印实验统计摘要（不依赖 pandas）。"""
        rows = self.read_all()
        if not rows:
            return None

        total = len(rows)
        passed = sum(1 for r in rows if r.get("status") == "pass")
        scores = [float(r["final_score"]) for r in rows if r.get("final_score")]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0

        lines = [
            f"  实验总数: {total}",
            f"  通过率:   {passed}/{total} ({passed/total*100:.1f}%)",
            f"  平均分:   {avg_score:.1f}",
            f"  最高分:   {max_score:.1f}",
        ]
        return "\n".join(lines)
