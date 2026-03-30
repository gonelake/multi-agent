#!/usr/bin/env bash
# install.sh — 安装 multi-agent-writer skill
#
# 一条命令完成：clone 项目代码 + 安装依赖 + 注册到各 AI agent
#
# 用法：
#   bash skills/install.sh                    # 自动检测已安装的 agent
#   bash skills/install.sh --agent all        # 安装到所有 agent
#   bash skills/install.sh --agent codebuddy
#   bash skills/install.sh --agent claude
#   bash skills/install.sh --agent openclaw
#
# 卸载：
#   rm -rf ~/.multi-agent-writer
#   rm -rf ~/.codebuddy/skills/multi-agent-writer
#   rm -rf ~/.claude/skills/multi-agent-writer
#   rm -rf ~/.openclaw/skills/multi-agent-writer

set -euo pipefail

SKILL_NAME="multi-agent-writer"
REPO_URL="https://github.com/gonelake/multi-agent.git"
INSTALL_DIR="${HOME}/.multi-agent-writer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_SKILL="${SCRIPT_DIR}/${SKILL_NAME}/SKILL.md"

# ── 1. 确保项目代码已就绪 ──────────────────────────────────
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    # 已有本地仓库，拉取最新
    git -C "${INSTALL_DIR}" pull --quiet
    echo "✓ 代码已更新: ${INSTALL_DIR}"
else
    # 首次安装，clone 项目
    echo "→ 正在 clone 项目代码..."
    git clone --quiet "${REPO_URL}" "${INSTALL_DIR}"
    echo "✓ 项目代码已下载: ${INSTALL_DIR}"
fi

# ── 2. 安装 Python 依赖 ────────────────────────────────────
if [[ -f "${INSTALL_DIR}/requirements.txt" ]]; then
    pip install --quiet -r "${INSTALL_DIR}/requirements.txt"
    echo "✓ Python 依赖已安装"
fi

# ── 3. 生成包含真实路径的 SKILL.md ────────────────────────
#    用 INSTALL_DIR 替换 SKILL.md 中的 <repo> 占位符
RESOLVED_SKILL="$(mktemp)"
sed "s|<repo>|${INSTALL_DIR}|g" "${SRC_SKILL}" > "${RESOLVED_SKILL}"

# ── 4. 注册到各 AI agent ───────────────────────────────────
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

install_skill_to() {
    local dest_dir="$1/${SKILL_NAME}"
    mkdir -p "${dest_dir}"
    cp "${RESOLVED_SKILL}" "${dest_dir}/SKILL.md"
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
                install_skill_to "${base_dir}"
                installed+=("${agent}")
            fi
            ;;
        all|"${agent}")
            install_skill_to "${base_dir}"
            installed+=("${agent}")
            ;;
    esac
done

rm -f "${RESOLVED_SKILL}"

if [[ ${#installed[@]} -eq 0 ]]; then
    echo "未检测到已安装的 agent，请指定：bash skills/install.sh --agent [codebuddy|claude|openclaw|all]" >&2
    exit 1
fi

echo "✓ skill 已注册到: ${installed[*]}"
echo ""
echo "立即体验（demo 模式，无需 API Key）："
echo "  cd ${INSTALL_DIR} && python main.py --demo"
echo ""
echo "生产模式请先配置 API Key："
echo "  cp ${INSTALL_DIR}/.env.example ${INSTALL_DIR}/.env"
echo "  # 编辑 .env，填入 LLM_API_KEY"
