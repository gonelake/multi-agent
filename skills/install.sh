#!/usr/bin/env bash
# install.sh — 将 multi-agent-writer skill 安装到本机各 AI agent 的 skills 目录
#
# 用法：
#   bash skills/install.sh              # 自动检测并安装到所有已安装的 agent
#   bash skills/install.sh --agent all  # 强制安装到所有 agent
#   bash skills/install.sh --agent codebuddy
#   bash skills/install.sh --agent claude
#   bash skills/install.sh --agent openclaw
#
# 卸载：
#   rm -rf ~/.codebuddy/skills/multi-agent-writer
#   rm -rf ~/.claude/skills/multi-agent-writer
#   rm -rf ~/.openclaw/skills/multi-agent-writer

set -euo pipefail

SKILL_NAME="multi-agent-writer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/${SKILL_NAME}"

# ── 检查源文件 ─────────────────────────────────────────────
if [[ ! -f "${SRC_DIR}/SKILL.md" ]]; then
    echo "错误: 找不到 ${SRC_DIR}/SKILL.md" >&2
    exit 1
fi

# ── 各 agent 名称和对应 skills 根目录（两个平行数组）──────
AGENT_NAMES=("codebuddy" "claude" "openclaw")
AGENT_BASE_DIRS=(
    "${HOME}/.codebuddy/skills"
    "${HOME}/.claude/skills"
    "${HOME}/.openclaw/skills"
)

# ── 解析参数 ───────────────────────────────────────────────
TARGET_AGENT="auto"   # auto = 仅安装到已检测到的 agent
if [[ $# -ge 1 && "$1" == "--agent" && $# -ge 2 ]]; then
    TARGET_AGENT="$2"
fi

# ── 安装函数 ───────────────────────────────────────────────
install_to() {
    local agent_name="$1"
    local dest_dir="$2/${SKILL_NAME}"
    mkdir -p "${dest_dir}"
    cp "${SRC_DIR}/SKILL.md" "${dest_dir}/SKILL.md"
    echo "  ✓ ${agent_name}: ${dest_dir}/SKILL.md"
}

# ── 检测 agent 是否存在（父目录存在即视为已安装）───────────
agent_exists() {
    local base_dir="$1"
    [[ -d "${base_dir}" ]] || [[ -d "$(dirname "${base_dir}")" ]]
}

# ── 执行安装 ───────────────────────────────────────────────
echo "安装 skill: ${SKILL_NAME}"
echo "  来源: ${SRC_DIR}"
echo ""

installed_count=0

for i in "${!AGENT_NAMES[@]}"; do
    agent="${AGENT_NAMES[$i]}"
    base_dir="${AGENT_BASE_DIRS[$i]}"

    case "${TARGET_AGENT}" in
        auto)
            # 自动模式：仅安装到已存在配置目录的 agent
            if agent_exists "${base_dir}"; then
                install_to "${agent}" "${base_dir}"
                installed_count=$((installed_count + 1))
            else
                echo "  - ${agent}: 未检测到安装，跳过 (${base_dir})"
            fi
            ;;
        all)
            # 强制安装到所有 agent
            install_to "${agent}" "${base_dir}"
            installed_count=$((installed_count + 1))
            ;;
        "${agent}")
            # 指定安装到该 agent
            install_to "${agent}" "${base_dir}"
            installed_count=$((installed_count + 1))
            ;;
    esac
done

echo ""
if [[ "${installed_count}" -eq 0 ]]; then
    echo "未检测到任何已安装的 agent，请手动指定目标："
    echo "  bash skills/install.sh --agent codebuddy"
    echo "  bash skills/install.sh --agent claude"
    echo "  bash skills/install.sh --agent openclaw"
    echo "  bash skills/install.sh --agent all"
    exit 1
fi

echo "安装完成，共安装到 ${installed_count} 个 agent。"
