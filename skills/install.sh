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

if [[ ! -f "${SRC_DIR}/SKILL.md" ]]; then
    echo "错误: 找不到 ${SRC_DIR}/SKILL.md" >&2
    exit 1
fi

AGENT_NAMES=("codebuddy" "claude" "openclaw")
AGENT_BASE_DIRS=(
    "${HOME}/.codebuddy/skills"
    "${HOME}/.claude/skills"
    "${HOME}/.openclaw/skills"
)

TARGET_AGENT="auto"
if [[ $# -ge 2 && "$1" == "--agent" ]]; then
    TARGET_AGENT="$2"
fi

install_to() {
    local dest_dir="$1/${SKILL_NAME}"
    mkdir -p "${dest_dir}"
    cp "${SRC_DIR}/SKILL.md" "${dest_dir}/SKILL.md"
}

agent_exists() {
    [[ -d "$1" ]] || [[ -d "$(dirname "$1")" ]]
}

installed=()

for i in "${!AGENT_NAMES[@]}"; do
    agent="${AGENT_NAMES[$i]}"
    base_dir="${AGENT_BASE_DIRS[$i]}"

    case "${TARGET_AGENT}" in
        auto)
            if agent_exists "${base_dir}"; then
                install_to "${base_dir}"
                installed+=("${agent}")
            fi
            ;;
        all|"${agent}")
            install_to "${base_dir}"
            installed+=("${agent}")
            ;;
    esac
done

if [[ ${#installed[@]} -eq 0 ]]; then
    echo "未检测到已安装的 agent，请指定：bash skills/install.sh --agent [codebuddy|claude|openclaw|all]" >&2
    exit 1
fi

echo "✓ ${SKILL_NAME} 已安装到: ${installed[*]}"
