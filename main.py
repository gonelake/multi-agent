"""
main.py — 多智能体协作系统入口

运行方式：
  python main.py                          # 使用 config.py 中的默认配置
  python main.py --topic 科技             # 覆盖领域
  python main.py --pass-threshold 90      # 覆盖审校通过线
  python main.py --description "baseline" # 记录实验描述

所有默认值在 config.py 的 CliDefaults 中修改。
LLM API Key 在项目根目录的 .env 文件中设置（参考 .env.example）。
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
from pathlib import Path

from base_agent import LLMClient
from config import CliDefaults, LLMConfig, LLMClientConfig, ReviewConfig, WorkflowConfig
from experiments import ExperimentTracker, ExperimentLog
from orchestrator import Orchestrator
from search import DuckDuckGoSearchClient


def _make_demo_llm() -> LLMClient:
    """返回 MockLLMClient，用于 --demo 模式（无需真实 API Key）。"""
    # 延迟导入，避免生产路径依赖 tests 目录
    sys.path.insert(0, str(Path(__file__).parent / "tests"))
    from mock_llm import MockLLMClient  # type: ignore
    return MockLLMClient()


def _load_dotenv() -> None:
    """加载项目根目录的 .env 文件（仅设置尚未存在的环境变量）。"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 仅在环境变量未显式设置时写入（环境变量 > .env）
            if key and key not in os.environ:
                os.environ[key] = value


def main():
    _load_dotenv()

    # ── 读取配置默认值 ──
    defaults = CliDefaults()
    workflow_defaults = WorkflowConfig()

    parser = argparse.ArgumentParser(
        description="多智能体协作系统 — 抓热点 → 写文章 → 审校",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--topic",         default=defaults.topic,
                        help=f"关注的领域 (默认: {defaults.topic})")
    parser.add_argument("--count",         type=int, default=defaults.hotspot_count,
                        help=f"抓取热点数量 (默认: {defaults.hotspot_count})")
    parser.add_argument("--style",         default=defaults.article_style,
                        help=f"文章风格 (默认: {defaults.article_style})")
    parser.add_argument("--words",         type=int, default=defaults.word_count,
                        help=f"目标字数 (默认: {defaults.word_count})")
    parser.add_argument("--max-revisions", type=int, default=defaults.max_revisions,
                        help=f"最大修改轮次 (默认: {defaults.max_revisions})")
    parser.add_argument("--output",        default=defaults.output_file,
                        help=f"输出文件路径 (默认: {defaults.output_file})")
    parser.add_argument("--pass-threshold", type=int, default=defaults.pass_threshold,
                        help=f"审校通过的最低分数 (默认: {defaults.pass_threshold}，范围 1-100)")
    parser.add_argument("--description",   default="",
                        help="本次实验的描述，追加到 experiments.tsv")
    parser.add_argument("--demo",           action="store_true",
                        help="使用 Mock LLM 运行演示（无需真实 API Key，约 1 秒完成）")
    args = parser.parse_args()

    # ── 初始化 LLM ──
    if args.demo:
        llm = _make_demo_llm()
        llm_model_name = "MockLLM (demo)"
    else:
        try:
            llm_config = LLMConfig.from_env()
        except ValueError as e:
            print(e)
            sys.exit(1)
        llm = LLMClient(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            model=llm_config.model,
            api_style=llm_config.api_style,
            client_config=LLMClientConfig(),
        )
        llm_model_name = llm_config.model

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║     多智能体协作系统 — Multi-Agent Pipeline          ║")
    print("╠══════════════════════════════════════════════════════╣")
    print(f"║  领域:       {args.topic:<40} ║")
    print(f"║  风格:       {args.style:<40} ║")
    print(f"║  目标字数:   {args.words:<40} ║")
    print(f"║  最大修改:   {args.max_revisions:<40} ║")
    print(f"║  审校通过线: {args.pass_threshold:<40} ║")
    print(f"║  模型:       {llm_model_name:<40} ║")
    print(f"║  搜索:       {'DuckDuckGo 实时抓取':<40} ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ── 创建配置、追踪器、协调器 ──
    review_config = ReviewConfig(pass_threshold=args.pass_threshold)
    tracker = ExperimentTracker(
        str(Path(__file__).parent / "experiments.tsv")
    )
    orchestrator = Orchestrator(
        llm=llm,
        max_revisions=args.max_revisions,
        verbose=True,
        review_config=review_config,
        search_client=DuckDuckGoSearchClient(),
    )

    # ── 运行工作流 ──
    run_start = time.time()
    result = orchestrator.run(
        topic=args.topic,
        hotspot_count=args.count,
        article_style=args.style,
        article_word_count=args.words,
    )
    execution_time = time.time() - run_start

    # ── 记录实验结果 ──
    tracker.log(
        ExperimentLog.from_workflow_result(
            result=result,
            topic=args.topic,
            word_count=args.words,
            description=args.description or ("demo" if args.demo else "production"),
            execution_time=execution_time,
            pass_threshold=args.pass_threshold,
        )
    )
    summary = tracker.summary()
    if summary:
        print("\n实验追踪统计:")
        print(summary)

    # ── 输出最终文章 ──
    if result.success and result.final_article:
        print("\n" + "═" * 60)
        print("最终文章")
        print("═" * 60)
        print(f"\n# {result.final_article.get('title', '')}\n")
        print(result.final_article.get("content", ""))
        print("\n" + "═" * 60)

        output = {
            "hotspots": result.hotspots,
            "selected_topic": result.selected_topic,
            "final_article": result.final_article,
            "review_history": result.review_history,
            "total_revisions": result.total_revisions,
            "total_time_seconds": round(result.total_time, 1),
        }
        output_path = Path(__file__).parent / args.output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n完整结果已保存至: {output_path.name}")

        # 同时保存 Markdown 格式文章
        article = result.final_article
        md_path = output_path.with_suffix(".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {article.get('title', '')}\n\n")
            f.write(article.get("content", ""))
            f.write("\n")
        print(f"Markdown 文章已保存至: {md_path.name}")
    else:
        print("\n工作流执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
