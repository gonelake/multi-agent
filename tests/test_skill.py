"""
test_skill.py — skill 相关测试

覆盖两类测试：
1. SKILL.md 内容合规性（frontmatter 字段、关键内容存在）
2. install.sh 安装脚本行为（正常安装、幂等重装、源文件缺失报错）
"""

import subprocess
import tempfile
import shutil
import os
from pathlib import Path

import pytest

# ── 路径常量 ──────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent.parent
SKILL_DIR   = REPO_ROOT / "skills" / "multi-agent-writer"
SKILL_MD    = SKILL_DIR / "SKILL.md"
INSTALL_SH  = REPO_ROOT / "skills" / "install.sh"


# ══════════════════════════════════════════════════════════
# 1. SKILL.md 内容合规性
# ══════════════════════════════════════════════════════════

class TestSkillMdContent:
    """验证 SKILL.md 符合 skill 规范，且包含本系统所需的关键信息。"""

    def setup_method(self):
        assert SKILL_MD.exists(), f"SKILL.md 不存在: {SKILL_MD}"
        self.content = SKILL_MD.read_text(encoding="utf-8")
        self.lines   = self.content.splitlines()

    # ── frontmatter ────────────────────────────────────────

    def test_has_yaml_frontmatter(self):
        """文件以 '---' 开头，存在 YAML frontmatter 块。"""
        assert self.lines[0].strip() == "---", "第一行应为 '---'"
        closing = next(
            (i for i, l in enumerate(self.lines[1:], start=1) if l.strip() == "---"),
            None,
        )
        assert closing is not None, "frontmatter 缺少关闭 '---'"

    def test_frontmatter_has_name(self):
        """frontmatter 包含 name 字段。"""
        assert "name: multi-agent-writer" in self.content

    def test_frontmatter_has_description(self):
        """frontmatter 包含 description 字段且以 'Use when' 开头。"""
        desc_line = next(
            (l for l in self.lines if l.startswith("description:")), None
        )
        assert desc_line is not None, "缺少 description 字段"
        assert "Use when" in desc_line, "description 应以 'Use when' 开头"

    def test_frontmatter_has_allowed_tools(self):
        """frontmatter 声明了 allowed-tools。"""
        assert "allowed-tools:" in self.content

    def test_description_not_summarizes_workflow(self):
        """description 只描述触发条件，不应包含工作流摘要关键词。"""
        desc_line = next(
            (l for l in self.lines if l.startswith("description:")), ""
        )
        # 检查 description 不泄露 skill 内部流程描述
        forbidden = ["phase", "loop", "cycle", "then", "->", "→"]
        lower = desc_line.lower()
        for word in forbidden:
            assert word not in lower, (
                f"description 不应包含流程描述词 '{word}'，"
                "否则 agent 可能跳过阅读 skill 主体"
            )

    # ── 关键内容 ───────────────────────────────────────────

    def test_contains_demo_command(self):
        """包含 demo 模式调用命令，方便 agent 快速验证。"""
        assert "--demo" in self.content

    def test_contains_repo_path_reference(self):
        """包含项目路径引用（<repo>/ 或绝对路径），agent 可定位项目目录。"""
        assert "<repo>" in self.content or "multi-agent" in self.content

    def test_contains_cli_params_table(self):
        """包含 CLI 参数说明表格。"""
        assert "--topic" in self.content
        assert "--words" in self.content
        assert "--pass-threshold" in self.content

    def test_contains_output_files(self):
        """说明了输出文件格式（output.json / output.md）。"""
        assert "output.json" in self.content
        assert "output.md"   in self.content

    def test_contains_python_api_example(self):
        """包含 Python 程序化调用示例。"""
        assert "Orchestrator" in self.content
        assert "orchestrator.run(" in self.content

    def test_contains_env_config(self):
        """包含 .env 环境变量配置说明。"""
        assert "LLM_API_KEY" in self.content

    def test_contains_bugfix_record(self):
        """包含已知问题与修复记录章节，防止 agent 踩同一个坑。"""
        assert "已知问题" in self.content or "Known Issues" in self.content

    def test_frontmatter_length_within_limit(self):
        """frontmatter 总长度不超过 1024 字符（skill 规范限制）。"""
        lines = self.lines
        end = next(i for i, l in enumerate(lines[1:], start=1) if l.strip() == "---")
        frontmatter = "\n".join(lines[: end + 1])
        assert len(frontmatter) <= 1024, (
            f"frontmatter 长度 {len(frontmatter)} 超过 1024 字符限制"
        )


# ══════════════════════════════════════════════════════════
# 2. install.sh 行为测试
# ══════════════════════════════════════════════════════════

class TestInstallScript:
    """验证 install.sh 的安装行为，使用临时目录隔离，不影响真实环境。

    支持的 agent 及目录：
      codebuddy: ~/.codebuddy/skills/
      claude:    ~/.claude/skills/
      openclaw:  ~/.openclaw/skills/
    """

    def setup_method(self):
        assert INSTALL_SH.exists(), f"install.sh 不存在: {INSTALL_SH}"
        assert SKILL_MD.exists(),   f"SKILL.md 不存在: {SKILL_MD}"
        # 临时 HOME 目录，避免污染真实环境
        self.tmp_home = tempfile.mkdtemp(prefix="test_skill_home_")

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def _dest(self, agent: str) -> Path:
        """返回指定 agent 的预期安装路径。"""
        dirs = {
            "codebuddy": ".codebuddy/skills",
            "claude":    ".claude/skills",
            "openclaw":  ".openclaw/skills",
        }
        return Path(self.tmp_home) / dirs[agent] / "multi-agent-writer" / "SKILL.md"

    def _run(self, args: list = None, env_overrides: dict = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = self.tmp_home
        if env_overrides:
            env.update(env_overrides)
        cmd = ["bash", str(INSTALL_SH)] + (args or [])
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    # ── 自动检测模式 ────────────────────────────────────────

    def test_auto_detects_existing_agents(self):
        """自动模式下，仅安装到已存在配置目录的 agent。"""
        # 只预建 codebuddy 的父目录
        os.makedirs(Path(self.tmp_home) / ".codebuddy", exist_ok=True)
        result = self._run()
        assert result.returncode == 0
        assert self._dest("codebuddy").exists(), "codebuddy 应被安装"
        assert not self._dest("claude").exists(), "claude 未检测到，不应安装"
        assert not self._dest("openclaw").exists(), "openclaw 未检测到，不应安装"

    def test_auto_no_agent_detected_fails(self):
        """自动模式下，无任何已安装 agent 时退出码非零。"""
        # tmp_home 全新，无任何 .codebuddy / .claude / .openclaw
        result = self._run()
        assert result.returncode != 0

    def test_install_output_contains_success_message(self):
        """安装成功时标准输出包含 skill 名称和目标 agent。"""
        os.makedirs(Path(self.tmp_home) / ".codebuddy", exist_ok=True)
        result = self._run()
        assert "multi-agent-writer" in result.stdout
        assert "codebuddy" in result.stdout

    # ── --agent 指定模式 ────────────────────────────────────

    def test_install_specific_agent_codebuddy(self):
        """--agent codebuddy 只安装到 codebuddy，不管目录是否存在。"""
        result = self._run(["--agent", "codebuddy"])
        assert result.returncode == 0
        assert self._dest("codebuddy").exists()
        assert not self._dest("claude").exists()
        assert not self._dest("openclaw").exists()

    def test_install_specific_agent_claude(self):
        """--agent claude 只安装到 claude。"""
        result = self._run(["--agent", "claude"])
        assert result.returncode == 0
        assert self._dest("claude").exists()
        assert not self._dest("codebuddy").exists()

    def test_install_specific_agent_openclaw(self):
        """--agent openclaw 只安装到 openclaw。"""
        result = self._run(["--agent", "openclaw"])
        assert result.returncode == 0
        assert self._dest("openclaw").exists()

    def test_install_all_agents(self):
        """--agent all 强制安装到所有 agent。"""
        result = self._run(["--agent", "all"])
        assert result.returncode == 0
        for agent in ("codebuddy", "claude", "openclaw"):
            assert self._dest(agent).exists(), f"{agent} 应被安装"

    def test_install_invalid_agent_fails(self):
        """指定不存在的 agent 名时退出码非零。"""
        result = self._run(["--agent", "unknown-agent"])
        assert result.returncode != 0

    # ── 内容和幂等性 ────────────────────────────────────────

    def test_installed_skill_has_repo_substituted(self):
        """安装后 SKILL.md 中的 <repo> 已被替换为实际路径（不再含占位符）。"""
        self._run(["--agent", "codebuddy"])
        content = self._dest("codebuddy").read_text(encoding="utf-8")
        assert "<repo>" not in content, "安装后不应残留 <repo> 占位符"

    def test_installed_skill_contains_real_path(self):
        """安装后 SKILL.md 中含有 .multi-agent-writer 真实路径。"""
        self._run(["--agent", "codebuddy"])
        content = self._dest("codebuddy").read_text(encoding="utf-8")
        assert ".multi-agent-writer" in content

    def test_install_idempotent(self):
        """重复安装（幂等性）不报错，SKILL.md 仍存在且无占位符。"""
        self._run(["--agent", "codebuddy"])
        result = self._run(["--agent", "codebuddy"])
        assert result.returncode == 0
        content = self._dest("codebuddy").read_text(encoding="utf-8")
        assert "<repo>" not in content

    def test_install_creates_parent_dirs(self):
        """目标 skills 目录不存在时，安装能自动创建。"""
        result = self._run(["--agent", "claude"])
        assert result.returncode == 0
        assert self._dest("claude").parent.is_dir()

    def test_install_fails_when_source_missing(self):
        """源 SKILL.md 不存在时，脚本以非零退出码报错。"""
        with tempfile.TemporaryDirectory() as fake_skills_dir:
            # 构造一个不含 SKILL.md 的临时 skills 目录
            fake_install = Path(fake_skills_dir) / "install.sh"
            # 将真实 install.sh 内容写入临时位置，但不复制 SKILL.md
            fake_install.write_text(INSTALL_SH.read_text(encoding="utf-8"))
            fake_install.chmod(0o755)

            env = os.environ.copy()
            env["HOME"] = self.tmp_home
            result = subprocess.run(
                ["bash", str(fake_install)],
                capture_output=True,
                text=True,
                env=env,
            )
        assert result.returncode != 0, "源文件缺失时应以非零退出码报错"
        assert "错误" in result.stderr or "error" in result.stderr.lower() or result.stderr
