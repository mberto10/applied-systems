#!/bin/bash
# Shared setup for Attention Diet eval cases. Sourced by each case's scaffold.sh.
# Runs as you, before Claude starts, with HOME set to the run's throwaway home.
set -euo pipefail

SHARED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$SHARED/../.." && pwd)"
VENV="$HOME/.cache/attention-diet-venv"      # the path every skill expects
REAL_HOME="$(eval echo "~$(id -un)")"          # your real home, not the throwaway one
LOCAL_VENV="$REAL_HOME/.cache/attention-diet-venv"

# Give the run the plugin's Python environment. Reuse your local one offline when it exists.
prepare_python() {
  if [ -x "$LOCAL_VENV/bin/python" ]; then
    "$LOCAL_VENV/bin/python" -m venv --without-pip "$VENV"
    SRC_SITE="$("$LOCAL_VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    DST_SITE="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    cp -R "$SRC_SITE/." "$DST_SITE/"
  else
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install -q -r "$PLUGIN/requirements.txt"
  fi
  "$VENV/bin/python" -c 'import jsonschema' >/dev/null
}

# Install the fictional contract `eval-diet` as the default, exactly as setup would leave it.
install_contract() {
  local target="$HOME/.config/attention-diet/contracts/eval-diet"
  mkdir -p "$target"
  chmod 700 "$HOME/.config/attention-diet" "$HOME/.config/attention-diet/contracts" "$target"
  cp "$SHARED/eval-diet.json" "$target/attention_contract.json"
  chmod 600 "$target/attention_contract.json"
  echo "eval-diet" > "$HOME/.config/attention-diet/default"
  "$VENV/bin/python" "$PLUGIN/scripts/contract.py" validate --contract "$target/attention_contract.json" >/dev/null
}
