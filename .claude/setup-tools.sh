#!/usr/bin/env bash
# يثبّت إضافات Claude Code المستخدمة في هذا المشروع. آمن لإعادة التشغيل.
# Installs the Claude Code extensions used in this project. Safe to re-run.
#
#   - claude-code-setup  (anthropics/claude-plugins-official)
#   - claude-mem         (thedotmack/claude-mem)  — local mode, no cloud sign-in
#   - Agent Reach        (Panniantong/Agent-Reach)
#   - Strix CLI + skills (usestrix/strix)
#
# Each step runs on its own: one failure does not stop the others.

set -u
export PATH="$HOME/.local/bin:$PATH"

CLAUDE_MEM_VERSION="15.7.0"
AGENT_REACH_VERSION="v1.6.0"
STRIX_VERSION="1.7.0"

failed=()
step() {
  local name=$1; shift
  printf '\n==> %s\n' "$name"
  if ! "$@"; then
    echo "!! failed: $name" >&2
    failed+=("$name")
  fi
}

ensure_uv() {
  command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
}

install_claude_code_setup() {
  claude plugin marketplace add anthropics/claude-plugins-official >/dev/null 2>&1 || true
  claude plugin install claude-code-setup@claude-plugins-official --scope user
}

install_claude_mem() {
  claude plugin marketplace add thedotmack/claude-mem >/dev/null 2>&1 || true
  # --provider claude: memory runs on the logged-in Claude account, no cmem.ai account.
  CLAUDE_MEM_ONLINE_OPTIN=false CI=1 \
    npx -y "claude-mem@${CLAUDE_MEM_VERSION}" install --ide claude-code --provider claude --no-auto-start </dev/null \
  && npx -y "claude-mem@${CLAUDE_MEM_VERSION}" telemetry disable </dev/null
}

install_agent_reach() {
  # The PyPI package named "agent-reach" is a different project: install from GitHub only.
  uv tool install --force \
    "https://github.com/Panniantong/Agent-Reach/releases/download/${AGENT_REACH_VERSION}/agent-reach.zip" \
  && agent-reach setup </dev/null >/dev/null
}

install_strix() {
  uv tool install --force "strix-agent==${STRIX_VERSION}" || return 1
  local tmp
  tmp=$(mktemp -d)
  git clone -q --depth 1 --branch "v${STRIX_VERSION}" https://github.com/usestrix/strix.git "$tmp" 2>/dev/null \
    || git clone -q --depth 1 https://github.com/usestrix/strix.git "$tmp" || { rm -rf "$tmp"; return 1; }
  mkdir -p "$HOME/.claude/skills"
  cp -r "$tmp"/skills/* "$HOME/.claude/skills/"
  rm -rf "$tmp"
}

step "uv"                ensure_uv
step "claude-code-setup" install_claude_code_setup
step "claude-mem"        install_claude_mem
step "Agent Reach"       install_agent_reach
step "Strix"             install_strix

if ((${#failed[@]})); then
  printf '\nDone with failures: %s\n' "${failed[*]}" >&2
  exit 1
fi
printf '\nAll extensions installed.\n'
