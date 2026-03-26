"""
orchestrator.py — 协调器：串联多个智能体的工作流

Orchestrator 是整个多智能体系统的"大脑"，负责：
1. 按顺序调度各智能体执行任务
2. 在智能体之间传递消息
3. 处理审校-修改循环（最多 N 轮）
4. 汇总最终结果
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from typing import Optional

from base_agent import AgentMessage, MessageType, LLMClient
from agents import ResearcherAgent, WriterAgent, ReviewerAgent
from config import ReviewConfig
from search import DuckDuckGoSearchClient


@dataclass
class WorkflowResult:
    """工作流最终输出"""
    success: bool
    hotspots: list[dict]         # 抓取到的热点列表
    selected_topic: dict         # 选中的话题
    final_article: dict          # 最终文章
    review_history: list[dict]   # 审校历史
    total_revisions: int         # 总修改轮次
    total_time: float            # 总耗时（秒）


class Orchestrator:
    """
    多智能体协调器。
    
    工作流程：
    ┌─────────────┐     ┌─────────────┐     ┌──────────────┐
    │  Researcher  │────▶│   Writer     │────▶│   Reviewer   │
    │  (抓取热点)   │     │  (撰写文章)   │◀───│  (审校文章)   │
    └─────────────┘     └─────────────┘  ↑  └──────────────┘
                              │          │         │
                              │  不通过？  │         │
                              └──────────┘         │
                              通过 ─────────────────┘
                                        ↓
                                   ┌─────────┐
                                   │  输出结果  │
                                   └─────────┘
    
    参数：
      - llm: LLM 客户端
      - max_revisions: 最大修改轮次（防止死循环）
      - verbose: 是否打印详细日志
      - review_config: 审校配置（通过阈值等），默认使用 ReviewConfig() 默认值
    """

    def __init__(
        self,
        llm: LLMClient,
        max_revisions: int = 2,
        verbose: bool = True,
        review_config: Optional[ReviewConfig] = None,
        search_client: Optional[DuckDuckGoSearchClient] = None,
    ):
        self.llm = llm
        self.max_revisions = max_revisions
        self.verbose = verbose
        self.review_config = review_config or ReviewConfig()

        # 初始化三个智能体
        self.researcher = ResearcherAgent(
            name="🔍 Researcher",
            llm=llm,
            search_client=search_client,
            verbose=verbose,
        )
        self.writer = WriterAgent(
            name="✍️ Writer",
            llm=llm,
            verbose=verbose,
        )
        self.reviewer = ReviewerAgent(
            name="📋 Reviewer",
            llm=llm,
            config=self.review_config,
            verbose=verbose,
        )

    def _print_divider(self, title: str):
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"  🔄 阶段: {title}")
            print(f"{'='*60}\n")

    def run(
        self,
        topic: str = "AI",
        hotspot_count: int = 5,
        article_style: str = "深度分析",
        article_word_count: int = 1000,
    ) -> WorkflowResult:
        """
        执行完整的多智能体协作工作流。
        
        Args:
            topic: 关注领域
            hotspot_count: 抓取热点数量
            article_style: 文章风格
            article_word_count: 目标字数
        
        Returns:
            WorkflowResult: 包含热点、文章、审校记录等完整结果
        """
        start_time = time.time()
        review_history = []

        # ──────────── 阶段 1: 热点抓取 ────────────
        self._print_divider("1/3 热点抓取")

        research_msg = AgentMessage(
            sender="orchestrator",
            receiver=self.researcher.name,
            msg_type=MessageType.TASK,
            payload={"topic": topic, "count": hotspot_count},
        )
        research_result = self.researcher.run(research_msg)

        if research_result.msg_type == MessageType.ERROR:
            return WorkflowResult(
                success=False, hotspots=[], selected_topic={},
                final_article={}, review_history=[], total_revisions=0,
                total_time=time.time() - start_time,
            )

        hotspots = research_result.payload.get("hotspots", [])
        selected = research_result.payload.get("selected", {})

        if self.verbose:
            print(f"\n📋 热点列表:")
            for i, h in enumerate(hotspots, 1):
                score = h.get("relevance_score", "?")
                print(f"  {i}. [{score}/10] {h.get('title', 'N/A')}")
            print(f"\n⭐ 选中话题: {selected.get('title', 'N/A')}")
            print(f"   理由: {selected.get('reason', 'N/A')}")

        # ──────────── 阶段 2: 撰写文章 ────────────
        self._print_divider("2/3 撰写文章")

        write_msg = AgentMessage(
            sender="orchestrator",
            receiver=self.writer.name,
            msg_type=MessageType.TASK,
            payload={
                "topic": selected,
                "style": article_style,
                "word_count": article_word_count,
                "revision": 0,
            },
        )
        write_result = self.writer.run(write_msg)

        if write_result.msg_type == MessageType.ERROR:
            return WorkflowResult(
                success=False, hotspots=hotspots, selected_topic=selected,
                final_article={}, review_history=[], total_revisions=0,
                total_time=time.time() - start_time,
            )

        current_article = write_result.payload
        revision_count = 0

        # ──────────── 阶段 3: 审校循环 ────────────
        while revision_count <= self.max_revisions:
            self._print_divider(
                f"3/3 审校文章 (第 {revision_count + 1} 轮)"
            )

            review_msg: AgentMessage = AgentMessage(
                sender="orchestrator",
                receiver=self.reviewer.name,
                msg_type=MessageType.TASK,
                payload={
                    "title": current_article.get("title", ""),
                    "content": current_article.get("content", ""),
                    "revision": revision_count,
                },
            )
            review_result = self.reviewer.run(review_msg)

            if review_result.msg_type == MessageType.ERROR:
                return WorkflowResult(
                    success=False, hotspots=hotspots, selected_topic=selected,
                    final_article=current_article, review_history=review_history,
                    total_revisions=revision_count, total_time=time.time() - start_time,
                )

            review_data = review_result.payload
            review_history.append({
                "revision": revision_count,
                "score": review_data.get("overall_score", 0),
                "approved": review_data.get("approved", False),
                "scores": review_data.get("scores", {}),
                "feedback": review_data.get("feedback", ""),
                "highlights": review_data.get("highlights", []),
            })

            # 如果通过审校，退出循环
            if review_data.get("approved", False):
                if self.verbose:
                    print(f"\n🎉 文章通过审校！最终得分: {review_data.get('overall_score', 0)}/100")
                break

            # 未通过 + 还有修改机会 → 让 Writer 评估并修改
            if revision_count < self.max_revisions:
                revision_count += 1
                self._print_divider(f"✏️ 修改文章 (第 {revision_count} 轮)")

                revise_msg = AgentMessage(
                    sender="orchestrator",
                    receiver=self.writer.name,
                    msg_type=MessageType.TASK,
                    payload={
                        "topic": selected,
                        "style": article_style,
                        "word_count": article_word_count,
                        "revision": revision_count,
                        "feedback": review_data.get("feedback", ""),
                        "original_title": current_article.get("title", ""),
                        "original_article": current_article.get("content", ""),
                    },
                )
                revise_result = self.writer.run(revise_msg)

                if revise_result.msg_type == MessageType.ERROR:
                    break

                revise_payload = revise_result.payload
                if not revise_payload.get("feedback_accepted", True):
                    # Writer 判断反馈价值不足，保留当前版本，不计入修改轮次
                    rejection = revise_payload.get("rejection_reason", "")
                    if self.verbose:
                        print(f"\n💡 Writer 判断反馈价值不足，跳过本轮修改。原因：{rejection}")
                    revision_count -= 1  # 回退计数，不算一次真实修改
                else:
                    current_article = revise_payload
            else:
                revision_count += 1
                if self.verbose:
                    print(f"\n⚠️ 已达最大修改次数 ({self.max_revisions})，使用当前版本。")

        total_time = time.time() - start_time

        # ──────────── 汇总结果 ────────────
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"  📊 工作流完成")
            print(f"{'='*60}")
            print(f"  ⏱️  总耗时: {total_time:.1f} 秒")
            print(f"  📝 修改轮次: {revision_count}")
            print(f"  📊 审校历史:")
            for r in review_history:
                status = "✅" if r["approved"] else "🔄"
                print(f"     第{r['revision']}版: {status} {r['score']}/100")
            print()

        return WorkflowResult(
            success=True,
            hotspots=hotspots,
            selected_topic=selected,
            final_article=current_article,
            review_history=review_history,
            total_revisions=revision_count,
            total_time=total_time,
        )
