#!/bin/bash

set -e

# Location of the BetterDisplay CLI
CLI="betterdisplaycli"

# Ensure BetterDisplay CLI is installed
command -v $CLI >/dev/null 2>&1 || exit 0

# Only proceed on macOS
[[ "$(uname)" == "Darwin" ]] || exit 0

# Only run on machines with an internal display
if ! system_profiler SPDisplaysDataType | grep -q "Connection Type: Internal"; then
  exit 0
fi

# Get internal built-in display info from system_profiler
INTERNAL=$(system_profiler SPDisplaysDataType | awk '
  BEGIN { found=0 }
  /Display Type:/ { display_type=$0 }
  /Resolution:/ {
    if (index(tolower(display_type),"built-in") > 0) {
      resolution=$2 "x" $4
      found=1
      print resolution
      exit
    }
  }
')

# If no internal display found, do nothing
if [[ -z "$INTERNAL" ]]; then
  exit 0
fi

# Parse native resolution
WIDTH=$(echo $INTERNAL | cut -dx -f1)
HEIGHT=$(echo $INTERNAL | cut -dx -f2)

# Compute half of native resolution for typical HiDPI
TARGET_WIDTH=$((WIDTH / 2))
TARGET_HEIGHT=$((HEIGHT / 2))

# Ensure BetterDisplay is running
if ! pgrep -x "BetterDisplay" >/dev/null; then
  open -g -a "BetterDisplay"
  sleep 2
fi

TARGET="${TARGET_WIDTH}x${TARGET_HEIGHT}"

CURRENT=$(betterdisplaycli get --display=internal --resolution 2>/dev/null | cut -d= -f2)

if [[ "$CURRENT" != "$TARGET" ]]; then
  betterdisplaycli set \
    --display=internal \
    --resolution="$TARGET" \
    --hidpi=on
fi

# Give BetterDisplay a moment to apply the mode
sleep 1

# Quit BetterDisplay cleanly
osascript -e 'tell application "BetterDisplay" to quit'
