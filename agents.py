"""
agents.py — 三个业务智能体的实现

1. ResearcherAgent (热点抓取) — 搜索并筛选时事热点
2. WriterAgent    (文章撰写) — 根据选题生成高质量文章
3. ReviewerAgent  (文章审校) — 检查文章质量并给出修改意见
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional, TypedDict
from base_agent import BaseAgent, AgentMessage, MessageType, LLMClient
from config import AgentConfig, ReviewConfig, SearchConfig
from search import DuckDuckGoSearchClient


# ══════════════════════════════════════════════
# Payload 类型定义（供 IDE 类型提示使用）
# ══════════════════════════════════════════════

class HotspotItem(TypedDict):
    title: str
    summary: str
    source: str
    relevance_score: int

class ResearcherOutputPayload(TypedDict):
    hotspots: list
    selected: dict          # 含 title, summary(可选), reason

class WriterOutputPayload(TypedDict, total=False):
    title: str
    titles: dict            # 含 A/B/C 三个备选标题
    content: str
    word_count: int
    revision: int
    feedback_accepted: bool
    rejection_reason: str

class ReviewerOutputPayload(TypedDict, total=False):
    approved: bool
    overall_score: int
    scores: dict
    feedback: str
    highlights: list


# ══════════════════════════════════════════════
# 智能体 1: 热点抓取 (Researcher)
# ══════════════════════════════════════════════

class ResearcherAgent(BaseAgent):
    """
    职责：根据给定主题/领域，搜索并整理当前时事热点。

    若注入了 search_client，先用 DuckDuckGo 搜索真实最新新闻，
    再把搜索结果交给 LLM 做筛选、评分、推荐选题（RAG 模式）。
    若未注入，退回到纯 LLM 生成（兼容 demo/测试模式）。

    输入 payload:
      - topic: str  — 关注的领域（如 "AI"、"科技"、"财经"）
      - count: int  — 期望热点数量（默认 5）

    输出 payload: ResearcherOutputPayload
    """

    SYSTEM_PROMPT_WITH_SEARCH = """你是一位资深的新闻编辑和热点分析师。
用户会提供一批从网络上实时抓取的新闻原文（含标题、摘要、来源链接、发布日期）。
你的任务是：
1. 从这些真实新闻中，筛选出最值得关注的热点（去除重复、低质量内容）
2. 为每个热点提供：中文标题、摘要（50字内）、信息来源网站、关注度评分(1-10)
3. 从中推荐 1 个最适合写深度文章的选题，并说明理由

重要：只基于提供的新闻内容输出，不要凭空编造内容。

输出 JSON 格式：
{
  "hotspots": [
    {"title": "...", "summary": "...", "source": "...", "url": "...", "relevance_score": 8}
  ],
  "selected": {
    "title": "...",
    "summary": "...",
    "reason": "为什么选这个作为文章选题"
  }
}"""

    SYSTEM_PROMPT_FALLBACK = """你是一位资深的新闻编辑和热点分析师。你的任务是：
1. 根据用户指定的领域，列出当前最值得关注的时事热点
2. 为每个热点提供：标题、摘要（50字内）、信息来源、关注度评分(1-10)
3. 从中推荐 1 个最适合写深度文章的选题，并说明理由

输出 JSON 格式：
{
  "hotspots": [
    {"title": "...", "summary": "...", "source": "...", "relevance_score": 8}
  ],
  "selected": {
    "title": "...",
    "reason": "为什么选这个作为文章选题"
  }
}"""

    def __init__(
        self,
        name: str,
        llm: LLMClient,
        search_client: Optional[DuckDuckGoSearchClient] = None,
        verbose: bool = True,
        agent_config: Optional[AgentConfig] = None,
        search_config: Optional[SearchConfig] = None,
    ):
        super().__init__(name, llm, verbose)
        self.search_client = search_client
        self._agent_cfg = agent_config or AgentConfig()
        self._search_cfg = search_config or SearchConfig()

    def _build_search_queries(self, topic: str) -> list[str]:
        """根据主题构造多个搜索关键词，覆盖更广的新闻面。"""
        return [
            f"{topic} 最新进展",
            f"{topic} 新闻",
            f"{topic} 发布 突破",
        ]

    def _format_search_results(self, results: list[dict]) -> str:
        """将搜索结果格式化为给 LLM 阅读的文本。"""
        lines = [f"以下是从网络实时抓取的 {len(results)} 条新闻（今天：{date.today().strftime('%Y年%m月%d日')}）：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"--- 新闻 {i} ---")
            lines.append(f"标题：{r['title']}")
            if r.get("published_date"):
                lines.append(f"发布时间：{r['published_date']}")
            lines.append(f"来源：{r['url']}")
            lines.append(f"内容摘要：{r['content'][:self._search_cfg.content_preview_len]}")
            lines.append("")
        return "\n".join(lines)

    def process(self, message: AgentMessage) -> AgentMessage:
        topic = message.payload.get("topic", "科技")
        count = message.payload.get("count", self._search_cfg.max_results)

        if self.search_client:
            # ── 真实搜索模式（RAG）──
            self.log(f"🌐 正在搜索「{topic}」领域最新新闻...")
            queries = self._build_search_queries(topic)
            raw_results = self.search_client.search_multi(
                queries,
                max_results_per_query=max(self._search_cfg.results_per_query, count),
                days=self._search_cfg.default_days,
            )
            self.log(f"📥 搜索返回 {len(raw_results)} 条原始新闻")

            # 提取并展示新闻的时间范围
            dates = sorted(
                r["published_date"] for r in raw_results if r.get("published_date")
            )
            if dates:
                fmt = lambda d: d[:10]  # 取 YYYY-MM-DD，去掉时区后缀
                if fmt(dates[0]) == fmt(dates[-1]):
                    self.log(f"📅 新闻时间: {fmt(dates[0])}")
                else:
                    self.log(f"📅 新闻时间: {fmt(dates[0])} ~ {fmt(dates[-1])}")

            if not raw_results:
                self.log("⚠️  搜索无结果，降级为 LLM 生成模式")
                result = self._llm_fallback(topic, count)
                return AgentMessage(
                    sender=self.name,
                    receiver="orchestrator",
                    msg_type=MessageType.RESULT,
                    payload=result,
                )

            search_text = self._format_search_results(raw_results)
            result = self.llm.chat_json(
                system_prompt=self.SYSTEM_PROMPT_WITH_SEARCH,
                user_prompt=(
                    f"{search_text}\n"
                    f"请从以上新闻中筛选出「{topic}」领域最值得关注的 {count} 条热点，"
                    f"并推荐 1 个最适合写深度文章的选题。"
                ),
                temperature=self._agent_cfg.researcher_with_search,
            )
        else:
            # ── 降级模式：纯 LLM 生成 ──
            result = self._llm_fallback(topic, count)

        self.log(f"📋 找到 {len(result.get('hotspots', []))} 条热点")
        self.log(f"⭐ 推荐选题: {result.get('selected', {}).get('title', 'N/A')}")

        return AgentMessage(
            sender=self.name,
            receiver="orchestrator",
            msg_type=MessageType.RESULT,
            payload=result,
        )

    def _llm_fallback(self, topic: str, count: int) -> dict:
        """降级：纯靠 LLM 知识生成热点（无真实搜索）。"""
        self.log(f"🔍 正在搜索「{topic}」领域的 {count} 条热点（LLM 模式）...")
        return self.llm.chat_json(
            system_prompt=self.SYSTEM_PROMPT_FALLBACK,
            user_prompt=(
                f"请列出当前「{topic}」领域最值得关注的 {count} 条时事热点。"
                f"今天的日期是 {date.today().strftime('%Y年%m月%d日')}。"
            ),
            temperature=self._agent_cfg.researcher_fallback,
        )


# ══════════════════════════════════════════════
# 智能体 2: 文章撰写 (Writer)
# ══════════════════════════════════════════════

class WriterAgent(BaseAgent):
    """
    职责：根据选定的热点话题，撰写一篇高质量文章。

    自主决策能力：
      收到审校反馈时，先用 LLM 评估反馈是否值得采纳。
      若判断价值不足，返回原文并附 feedback_accepted=False，
      Orchestrator 将跳过本轮修改，保留当前最优版本。

    输入 payload:
      - topic: dict           — 选定的话题（含 title, summary 等）
      - style: str            — 文章风格（默认 "深度分析"）
      - word_count: int       — 目标字数（默认 1000）
      - feedback: str         — (可选) 审校意见，用于修改稿件
      - original_title: str   — (可选) 原文标题，供评估时使用
      - original_article: str — (可选) 原文内容，拒绝修改时原样返回

    输出 payload: WriterOutputPayload
    """

    SYSTEM_PROMPT = """你是一位资深的微信公众号科技专栏作家，拥有10万+爆款文章经验。

## 写作原则

1. **移动端优先**：读者在手机上阅读，注意力极短，必须在3秒内抓住眼球
2. **口语化表达**：像和朋友聊天一样写作，拒绝学术腔和官方话术
3. **信息密度高**：每一段都要有信息增量，绝不注水

## 排版规范（手机端适配）

- 每段不超过3-4行（手机屏幕约60-80字换段）
- 段间空一行，保证呼吸感
- 重点内容用**加粗**强调，每段最多加粗1处
- 善用短句和句号断句，少用逗号连接长句
- 禁止大段引用和长列表，列表项不超过5条
- 小标题用简短有力的短语，不超过10个字

## 文章结构

1. **开头（钩子）**：用一个反常识的事实、争议性观点或具体场景切入，50字内必须制造冲突或好奇
2. **背景铺垫**：快速交代"发生了什么"，不超过2段
3. **核心分析（2-3个论点）**：每个论点 = 观点 + 案例/数据 + 一句话总结。论点之间用小标题分隔
4. **影响解读**：这件事和普通读者有什么关系？用"你"来拉近距离
5. **结尾金句**：一句有力的总结或开放性问题，引发转发欲望

## 标题技巧

提供3个备选标题，风格分别为：
- A. 悬念型（引发好奇）
- B. 观点型（态度鲜明）
- C. 利益型（和读者相关）

## 语言风格

- 多用类比和比喻，把复杂概念翻译成生活常识
- 适度使用反问句，制造节奏感
- 可以偶尔用网络热梗，但不滥用
- 关键数据用阿拉伯数字呈现（如"3倍""90%"），比汉字数字更抓眼球
- 避免"众所周知""不言而喻"等空话套话

## 禁忌

- 不写超过800字的文章（公众号完读率在600-1000字最优）
- 不堆砌术语，每个专业词首次出现必须用一句话解释
- 不写没有观点的纯资讯搬运
- 不用"震惊""重磅"等低质标题词

请直接输出 JSON：
{
  "titles": {
    "A": "悬念型标题",
    "B": "观点型标题",
    "C": "利益型标题"
  },
  "title": "从A/B/C中选最优的一个作为正式标题",
  "content": "文章正文（使用 Markdown 格式）",
  "word_count": 实际字数
}"""

    REVISE_PROMPT = """你是一位资深的微信公众号科技专栏作家，拥有10万+爆款文章经验。
现在需要根据审校意见修改文章，保持公众号风格：短段落、口语化、信息密度高。
认真对待每一条修改建议，保持文章原有的优点，改进不足之处。

请直接输出修改后的 JSON：
{
  "titles": {
    "A": "悬念型标题",
    "B": "观点型标题",
    "C": "利益型标题"
  },
  "title": "从A/B/C中选最优的一个作为正式标题",
  "content": "修改后的文章正文（Markdown 格式）",
  "word_count": 实际字数
}"""

    EVALUATE_PROMPT = """你是一位资深编辑，负责评估审校反馈是否值得采纳。

判断标准：
- 值得采纳：反馈包含具体的、可操作的改进建议（如"补充数据"、"增加案例"、"修改结构"、"丰富论据"）
- 不值得采纳：反馈过于模糊（如"写得不够好"）、仅涉及无关紧要的格式小问题、或建议方向与文章核心矛盾

请输出 JSON：
{
  "should_revise": true,
  "reason": "一句话说明判断理由"
}"""

    def __init__(
        self,
        name: str,
        llm: LLMClient,
        verbose: bool = True,
        agent_config: Optional[AgentConfig] = None,
    ):
        super().__init__(name, llm, verbose)
        self._agent_cfg = agent_config or AgentConfig()

    def _evaluate_feedback(self, feedback: str, article_title: str) -> tuple:
        """
        调用 LLM 评估反馈是否值得采纳。
        返回 (should_revise: bool, reason: str)
        默认接受（True），确保在 LLM 解析异常时不丢弃合理反馈。
        """
        try:
            result = self.llm.chat_json(
                system_prompt=self.EVALUATE_PROMPT,
                user_prompt=f"文章标题：{article_title}\n\n审校反馈：\n{feedback}",
                temperature=self._agent_cfg.writer_eval,
            )
            return result.get("should_revise", True), result.get("reason", "")
        except Exception as e:
            self.log(f"⚠️  反馈评估失败，默认接受: {e}")
            return True, ""

    def process(self, message: AgentMessage) -> AgentMessage:
        topic = message.payload.get("topic", {})
        style = message.payload.get("style", "深度分析")
        word_count = message.payload.get("word_count", 1000)
        feedback = message.payload.get("feedback", "")
        revision = message.payload.get("revision", 0)

        if feedback:
            original_title = message.payload.get("original_title", "")
            original = message.payload.get("original_article", "")

            # ── 自主决策：评估反馈价值 ──
            should_revise, eval_reason = self._evaluate_feedback(feedback, original_title)

            if not should_revise:
                # 拒绝：返回原文，通知 Orchestrator 跳过本轮修改
                self.log(f"💡 反馈价值不足，跳过修改（第 {revision} 轮）：{eval_reason}")
                return AgentMessage(
                    sender=self.name,
                    receiver="orchestrator",
                    msg_type=MessageType.RESULT,
                    payload={
                        "title": original_title,
                        "content": original,
                        "word_count": len(original),
                        "revision": revision,
                        "feedback_accepted": False,
                        "rejection_reason": eval_reason,
                    },
                )

            # 接受：正常进入修改流程
            self.log(f"✅ 反馈有价值，开始修改（第 {revision} 轮）：{eval_reason}")
            result = self.llm.chat_json(
                system_prompt=self.REVISE_PROMPT,
                user_prompt=(
                    f"## 原文\n{original}\n\n"
                    f"## 审校意见\n{feedback}\n\n"
                    f"请根据以上意见修改文章，目标字数约 {word_count} 字。"
                ),
                temperature=self._agent_cfg.writer_revise,
            )
            result["feedback_accepted"] = True
        else:
            # 初稿模式
            self.log(f"📝 正在撰写关于「{topic.get('title', '')}」的{style}文章...")
            result = self.llm.chat_json(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=(
                    f"请写一篇关于以下话题的{style}文章，目标字数约 {word_count} 字。\n\n"
                    f"话题：{topic.get('title', '')}\n"
                    f"背景：{topic.get('summary', '')}\n"
                    f"推荐理由：{topic.get('reason', '')}"
                ),
                temperature=self._agent_cfg.writer_draft,
            )

        result["revision"] = revision
        content = result.get("content", "")
        # 中文文章按字符数计（去除空白和标点），比 len() 更贴近"字数"概念
        actual_words = len(re.sub(r"[\s\W]", "", content))
        self.log(f"📄 文章完成: 「{result.get('title', '')}」({actual_words} 字, 第{revision}版)")
        # 展示备选标题
        titles = result.get("titles", {})
        if titles:
            self.log("📌 备选标题:")
            for style_key, t in titles.items():
                self.log(f"   {style_key}. {t}")

        return AgentMessage(
            sender=self.name,
            receiver="orchestrator",
            msg_type=MessageType.RESULT,
            payload=result,
        )


# ══════════════════════════════════════════════
# 智能体 3: 文章审校 (Reviewer)
# ══════════════════════════════════════════════

class ReviewerAgent(BaseAgent):
    """
    职责：审校文章质量，给出评分和修改意见。

    输入 payload:
      - title: str    — 文章标题
      - content: str  — 文章正文
      - revision: int — 当前修改轮次

    输出 payload: ReviewerOutputPayload
    """

    # system prompt 模板，评分维度和通过标准从 config 动态生成
    _SYSTEM_PROMPT_TEMPLATE = """你是一位资深的微信公众号主编，专注科技内容，拥有评判10万+爆款文章的经验。
你的评审视角是：文章是否适合在手机上阅读并被转发传播？

请从以下维度审校文章：

{dimension_prompt}

评分标准：
{score_description}

评审时请注意：
- 口语化、短段落、节奏感是公众号的核心，不要用学术标准苛求
- 类比和比喻是优点，不是不严谨
- 标题夸张程度以是否失实为界，有感染力但不失实是允许的
- 事实准确性只要逻辑合理、数量级正确即可，无需苛求每个数据都有注脚

请输出 JSON：
{{
  "approved": true/false,
  "overall_score": 85,
  "scores": {{
    "content_insight": 25,
    "readability": 20,
    "title_appeal": 17,
    "structure_flow": 13,
    "accuracy": 10
  }},
  "feedback": "如果未通过，这里给出具体修改建议（逐条列出）",
  "highlights": ["文章的亮点1", "亮点2"]
}}"""

    def __init__(
        self,
        name: str,
        llm: LLMClient,
        config: Optional[ReviewConfig] = None,
        verbose: bool = True,
        agent_config: Optional[AgentConfig] = None,
    ):
        super().__init__(name, llm, verbose)
        self.config = config or ReviewConfig()
        self._agent_cfg = agent_config or AgentConfig()
        # 在初始化时根据 config 生成 system prompt，避免每次调用重复构建
        self._system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(
            dimension_prompt=self.config.dimension_prompt(),
            score_description=self.config.score_description(),
        )

    def process(self, message: AgentMessage) -> AgentMessage:
        title = message.payload.get("title", "")
        content = message.payload.get("content", "")
        revision = message.payload.get("revision", 0)

        self.log(f"🔎 正在审校文章「{title}」(第{revision}版，通过线: {self.config.pass_threshold}分)...")

        result = self.llm.chat_json(
            system_prompt=self._system_prompt,
            user_prompt=(
                f"请审校以下文章：\n\n"
                f"## {title}\n\n"
                f"{content}"
            ),
            temperature=self._agent_cfg.reviewer,
        )

        # 使用 config 的阈值判断是否通过，而非依赖 LLM 的 approved 字段
        score = result.get("overall_score", 0)
        approved = score >= self.config.pass_threshold
        result["approved"] = approved

        status = "✅ 通过" if approved else "🔄 需修改"
        self.log(f"📊 审校结果: {status} (得分: {score}/100，通过线: {self.config.pass_threshold})")

        if result.get("highlights"):
            for h in result["highlights"]:
                self.log(f"  💎 亮点: {h}")

        if not approved and result.get("feedback"):
            self.log(f"  📝 修改意见: {result['feedback'][:100]}...")

        return AgentMessage(
            sender=self.name,
            receiver="orchestrator",
            msg_type=MessageType.RESULT,
            payload=result,
        )
