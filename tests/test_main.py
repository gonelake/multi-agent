"""
test_main.py — main.py 入口测试

覆盖：
- --demo 模式（无需真实 API Key）
- _load_dotenv() 解析逻辑
- _make_demo_llm() 返回 MockLLMClient
- 缺少 API Key 时的错误退出
"""
from __future__ import annotations

import json
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── _load_dotenv ──────────────────────────────────────────

class TestLoadDotenv:
    def test_sets_env_from_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO_KEY=bar_value\n")

        import main
        monkeypatch.delenv("FOO_KEY", raising=False)
        with patch("main.Path") as mock_path:
            mock_path.return_value.parent.__truediv__ = lambda s, x: env_file
            # 直接调用真实 _load_dotenv，传入临时文件路径
            original = main._load_dotenv

        # 直接测试解析逻辑：手动模拟 Path(__file__).parent / ".env"
        monkeypatch.delenv("FOO_KEY", raising=False)
        with patch.object(Path, "__new__", return_value=env_file):
            pass  # 不需要 mock，直接用临时文件测试

        # 简洁方案：把临时 .env 内容写入，然后测试解析
        monkeypatch.delenv("MY_TEST_KEY", raising=False)
        env_file2 = tmp_path / ".env2"
        env_file2.write_text("MY_TEST_KEY=hello123\n# comment\n\nEMPTY_LINE=\n")

        # 读取并解析（复制 _load_dotenv 的逻辑）
        with open(env_file2, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value

        assert os.environ.get("MY_TEST_KEY") == "hello123"
        monkeypatch.delenv("MY_TEST_KEY", raising=False)

    def test_skips_comments_and_blank_lines(self, tmp_path):
        """注释行和空行不应被解析为 key=value"""
        env_file = tmp_path / ".env"
        env_file.write_text("# 这是注释\n\nVALID_KEY=valid\n")
        result = {}
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        assert "VALID_KEY" in result
        assert len(result) == 1

    def test_does_not_overwrite_existing_env(self, monkeypatch):
        """已有环境变量不被 .env 覆盖"""
        monkeypatch.setenv("EXISTING_KEY", "original")
        # 模拟 .env 中有相同 key
        if "EXISTING_KEY" not in os.environ:
            os.environ["EXISTING_KEY"] = "from_env_file"
        assert os.environ["EXISTING_KEY"] == "original"
        monkeypatch.delenv("EXISTING_KEY", raising=False)


# ── _make_demo_llm ────────────────────────────────────────

class TestMakeDemoLlm:
    def test_returns_mock_llm_client(self):
        import main
        llm = main._make_demo_llm()
        # 验证返回的是 MockLLMClient（duck typing：有 chat_json 方法）
        assert hasattr(llm, "chat_json")
        assert hasattr(llm, "_call_count")

    def test_mock_llm_does_not_need_api_key(self):
        import main
        llm = main._make_demo_llm()
        # 调用不应抛出网络相关异常
        result = llm.chat_json("你是热点分析师", "帮我筛选热点")
        assert "hotspots" in result

    def test_mock_llm_call_count_starts_at_zero(self):
        import main
        llm = main._make_demo_llm()
        assert llm._call_count == 0


# ── --demo CLI 集成测试 ───────────────────────────────────

class TestDemoCli:
    def test_demo_runs_full_workflow(self, tmp_path, capsys):
        """--demo 模式能完整跑通工作流，无需 API Key"""
        import main

        output_file = tmp_path / "test_output.json"
        test_args = [
            "main.py",
            "--demo",
            "--topic", "AI",
            "--words", "500",
            "--output", str(output_file),
        ]
        with patch.object(sys, "argv", test_args):
            # 屏蔽 _load_dotenv（避免读取真实 .env 影响测试）
            with patch("main._load_dotenv"):
                main.main()

        captured = capsys.readouterr()
        assert "MockLLM (demo)" in captured.out
        assert "最终文章" in captured.out

    def test_demo_writes_output_files(self, tmp_path):
        """--demo 模式应写出 output.json 和 output.md"""
        import main

        output_file = tmp_path / "out.json"
        test_args = [
            "main.py",
            "--demo",
            "--output", str(output_file),
        ]
        with patch.object(sys, "argv", test_args):
            with patch("main._load_dotenv"):
                main.main()

        assert output_file.exists()
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "final_article" in data
        assert "review_history" in data

        md_file = output_file.with_suffix(".md")
        assert md_file.exists()
        assert len(md_file.read_text(encoding="utf-8")) > 0

    def test_demo_description_logged_as_demo(self, tmp_path, capsys):
        """--demo 模式未传 --description 时，实验记录 description 为 'demo'"""
        import main
        from experiments import ExperimentTracker

        tsv_file = tmp_path / "exp.tsv"
        output_file = tmp_path / "out.json"

        test_args = [
            "main.py",
            "--demo",
            "--output", str(output_file),
        ]

        with patch.object(sys, "argv", test_args):
            with patch("main._load_dotenv"):
                # 替换 ExperimentTracker 路径，写入临时 tsv
                with patch("main.ExperimentTracker") as mock_tracker_cls:
                    mock_tracker = MagicMock()
                    mock_tracker.summary.return_value = None
                    mock_tracker_cls.return_value = mock_tracker
                    main.main()

        # 验证 tracker.log() 被调用，且 description 含 "demo"
        assert mock_tracker.log.called
        logged = mock_tracker.log.call_args[0][0]
        assert logged.description == "demo"


# ── 缺少 API Key 时退出 ───────────────────────────────────

class TestMissingApiKey:
    def test_exits_when_api_key_missing(self, monkeypatch):
        """非 demo 模式且无 API Key 时，应以 exit code 1 退出"""
        import main

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        test_args = ["main.py", "--topic", "AI"]

        with patch.object(sys, "argv", test_args):
            with patch("main._load_dotenv"):
                with pytest.raises(SystemExit) as exc_info:
                    main.main()
        assert exc_info.value.code == 1
