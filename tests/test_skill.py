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

    def test_contains_system_path(self):
        """包含系统绝对路径，agent 可直接定位项目目录。"""
        assert "/Users/landwei/Documents/AI/multi-agent" in self.content

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
    """验证 install.sh 的安装行为，使用临时目录隔离，不影响真实 ~/.codebuddy。"""

    def setup_method(self):
        assert INSTALL_SH.exists(), f"install.sh 不存在: {INSTALL_SH}"
        assert SKILL_MD.exists(),   f"SKILL.md 不存在: {SKILL_MD}"
        # 临时 HOME 目录，避免污染真实环境
        self.tmp_home = tempfile.mkdtemp(prefix="test_skill_home_")

    def teardown_method(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def _run(self, env_overrides: dict = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = self.tmp_home
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            ["bash", str(INSTALL_SH)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_install_succeeds(self):
        """正常安装返回退出码 0。"""
        result = self._run()
        assert result.returncode == 0, f"安装失败:\n{result.stderr}"

    def test_install_creates_skill_file(self):
        """安装后目标路径存在 SKILL.md。"""
        self._run()
        dest = Path(self.tmp_home) / ".codebuddy" / "skills" / "multi-agent-writer" / "SKILL.md"
        assert dest.exists(), f"SKILL.md 未被安装到 {dest}"

    def test_installed_content_matches_source(self):
        """安装后的文件内容与源文件一致。"""
        self._run()
        dest = Path(self.tmp_home) / ".codebuddy" / "skills" / "multi-agent-writer" / "SKILL.md"
        assert dest.read_text(encoding="utf-8") == SKILL_MD.read_text(encoding="utf-8")

    def test_install_output_contains_success_message(self):
        """安装成功时标准输出包含完成提示。"""
        result = self._run()
        assert "安装完成" in result.stdout or "installed" in result.stdout.lower()

    def test_install_idempotent(self):
        """重复安装（幂等性）不报错，文件内容仍正确。"""
        self._run()
        result = self._run()
        assert result.returncode == 0
        dest = Path(self.tmp_home) / ".codebuddy" / "skills" / "multi-agent-writer" / "SKILL.md"
        assert dest.read_text(encoding="utf-8") == SKILL_MD.read_text(encoding="utf-8")

    def test_install_creates_parent_dirs(self):
        """即使 ~/.codebuddy/skills/ 目录不存在，安装也能自动创建。"""
        # tmp_home 是全新目录，不含任何子目录
        result = self._run()
        assert result.returncode == 0
        dest_dir = Path(self.tmp_home) / ".codebuddy" / "skills" / "multi-agent-writer"
        assert dest_dir.is_dir()

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
