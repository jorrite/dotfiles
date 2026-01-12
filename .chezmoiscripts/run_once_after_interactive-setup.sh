#!/usr/bin/env bash
set -e

echo "=== Mac setup interactive helper ==="
echo

# Function to open an app and give instructions
open_with_instructions() {
  local app_name="$1"
  local instructions="$2"

  echo "--------------------------------------------------"
  echo "Opening $app_name..."
  echo
  echo "$instructions"
  echo
  echo "Press Enter to open the app and apply the above steps..."
  read -r
  open -a "$app_name"
  echo "Press Enter to continue to the next instructions..."
  read -r
}

# === Karabiner-Elements ===
open_with_instructions "Karabiner-Elements" \
"Karabiner-Elements needs Input Monitoring and Accessibility permissions.
Go to System Settings → Privacy & Security and allow Karabiner."

echo
echo "✅ Setup guide complete! All apps have been opened for configuration."
echo "You can now continue with any remaining manual setup."
