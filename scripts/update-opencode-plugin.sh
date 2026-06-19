#!/usr/bin/env bash
# One-shot update: OpenCode global plugin dir + agents + pip
set -euo pipefail

REF="${1:-main}"
PLUGIN_DIR="${OPENCODE_PLUGIN_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode/plugins/sdk-forge}"
AGENTS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/agents"

if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "Plugin dir not found: $PLUGIN_DIR"
  echo "First install: git clone --branch $REF https://github.com/weininghui/TestAgent.git \"$PLUGIN_DIR\""
  exit 1
fi

cd "$PLUGIN_DIR"
git fetch origin
if [[ "$REF" == "main" ]]; then
  git checkout main
  git reset --hard origin/main
else
  git fetch --tags
  git checkout "$REF"
fi

python3 -m pip install -r requirements.txt -q
python3 -m pip install -e . --force-reinstall -q

mkdir -p "$AGENTS_DIR"
cp -f .opencode/agents/forge*.md "$AGENTS_DIR/"

python3 -c "import sdk_forge; print('sdk_forge', sdk_forge.__version__)"

echo ""
echo "Done. Fully quit OpenCode and reopen (MCP does not hot-reload)."
