#!/usr/bin/env bash
# install.sh — 将 multi-agent-writer skill 安装到本机 CodeBuddy Code skills 目录
#
# 用法：
#   bash skills/install.sh
#
# 效果：
#   将 skills/multi-agent-writer/SKILL.md 复制到
#   ~/.codebuddy/skills/multi-agent-writer/SKILL.md
#
# 卸载：
#   rm -rf ~/.codebuddy/skills/multi-agent-writer

set -euo pipefail

SKILL_NAME="multi-agent-writer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/${SKILL_NAME}"
DEST_DIR="${HOME}/.codebuddy/skills/${SKILL_NAME}"

echo "安装 skill: ${SKILL_NAME}"
echo "  来源: ${SRC_DIR}"
echo "  目标: ${DEST_DIR}"

# 检查源文件
if [[ ! -f "${SRC_DIR}/SKILL.md" ]]; then
    echo "错误: 找不到 ${SRC_DIR}/SKILL.md" >&2
    exit 1
fi

# 创建目标目录并复制
mkdir -p "${DEST_DIR}"
cp "${SRC_DIR}/SKILL.md" "${DEST_DIR}/SKILL.md"

echo "✓ 安装完成: ${DEST_DIR}/SKILL.md"
echo ""
echo "验证安装:"
echo "  head -3 ${DEST_DIR}/SKILL.md"
