#!/bin/bash

set -e

# Setup fish shell
echo "> Using fish shell"

# Check if fish is the default shell
if [ "$SHELL" != "/opt/homebrew/bin/fish" ]; then
    echo /opt/homebrew/bin/fish | sudo tee -a /etc/shells
    chsh -s /opt/homebrew/bin/fish
fi

# Close any open System Settings panes -
# this is to prevent them from overriding settings we’re about to change
osascript -e 'tell application "System Settings" to quit'

# Always show sound in menubar
defaults write $HOME/Library/Preferences/ByHost/com.apple.controlcenter.plist "Sound" -int 2
# Always show bluetooth in menubar
defaults write $HOME/Library/Preferences/ByHost/com.apple.controlcenter.plist "Bluetooth" -int 2

defaults write com.apple.menuextra.clock "Show24Hour" -bool "true"
defaults write com.apple.menuextra.clock "ShowDate" -bool "true"
defaults write com.apple.menuextra.clock "ShowDayOfWeek" -bool "true"
defaults write com.apple.menuextra.clock "ShowSeconds" -bool "true"

killall ControlCenter
