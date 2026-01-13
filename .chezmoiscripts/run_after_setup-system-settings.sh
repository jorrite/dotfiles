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
# Hide spotlight
defaults -currentHost write com.apple.Spotlight MenuItemHidden -int 1

# Clock settings
defaults write com.apple.menuextra.clock "Show24Hour" -bool "true"
defaults write com.apple.menuextra.clock "ShowDate" -bool "true"
defaults write com.apple.menuextra.clock "ShowDayOfWeek" -bool "true"
defaults write com.apple.menuextra.clock "ShowSeconds" -bool "true"

# Require password immediately after sleep or screen saver begins
defaults write com.apple.screensaver askForPassword -int 1
defaults write com.apple.screensaver askForPasswordDelay -int 0

# Allow keyboard navigation on prompts/modals
defaults write NSGlobalDomain AppleKeyboardUIMode -int 3

# Check for software updates daily
defaults write com.apple.SoftwareUpdate ScheduleFrequency -int 1

# Use column view in Finder
defaults write com.apple.finder FXPreferredViewStyle -string "clmv"
defaults write com.apple.finder FXPreferredGroupBy -string "Date Last Opened"

# Empty Trash securely by default
defaults write com.apple.finder EmptyTrashSecurely -bool true

# Disable recent applications in Dock
defaults write com.apple.dock "show-recents" -bool false

# Expand save panel by default
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode -bool true
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode2 -bool true

# Expand print panel by default
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint -bool true
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint2 -bool true

# Automatically quit printer app once the print jobs complete
defaults write com.apple.print.PrintingPrefs "Quit When Finished" -bool true

# Press Tab to highlight each item on a web page
defaults write com.apple.Safari WebKitTabToLinksPreferenceKey -bool true
defaults write com.apple.Safari com.apple.Safari.ContentPageGroupIdentifier.WebKit2TabsToLinks -bool true
# Enable Safari’s debug menu
defaults write com.apple.Safari IncludeInternalDebugMenu -bool true
# Enable the Develop menu and the Web Inspector in Safari
defaults write com.apple.Safari IncludeDevelopMenu -bool true
defaults write com.apple.Safari WebKitDeveloperExtrasEnabledPreferenceKey -bool true
defaults write com.apple.Safari com.apple.Safari.ContentPageGroupIdentifier.WebKit2DeveloperExtrasEnabled -bool true
# Disable Safari AutoFill
defaults write com.apple.Safari AutoFillPasswords -bool false
defaults write com.apple.Safari AutoFillCreditCardData -bool false
defaults write com.apple.Safari AutoFillMiscellaneousForms -bool false
# Enable “Do Not Track”
defaults write com.apple.Safari SendDoNotTrackHTTPHeader -bool true
# Update extensions automatically
defaults write com.apple.Safari InstallExtensionUpdatesAutomatically -bool true

dockutil --remove all --no-restart

dockutil --add "/Applications/Messages.app" --no-restart
dockutil --add "/Applications/Mail.app" --no-restart
dockutil --add "/Applications/Calendar.app" --no-restart
dockutil --add "/Applications/Things.app" --no-restart
dockutil --add "/Applications/Safari.app" --no-restart

dockutil --add "$HOME/Downloads" --view fan --display stack --sort dateadded --no-restart

for app in "ControlCenter" "SystemUIServer" "Dock" "Finder"; do
  killall "${app}" > /dev/null 2>&1
done
