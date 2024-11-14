#!/bin/bash

set -e

# Bootstrap script for new machines

xcode-select --install || echo "XCode already installed"

if which -s brew; then
    echo 'Homebrew is already installed'
else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    (
        echo
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"'
    ) >>$HOME/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

if type op >/dev/null 2>&1; then
    echo "1Password and 1Password CLI is already installed"
else
    brew install --cask 1password
    brew install 1password-cli
fi

echo "Please open 1Password, log into all accounts and set under Settings>CLI activate Integrate with 1Password CLI."
read -n 1 -r -s -p "Press any key to continue..."
echo

brew install chezmoi
chezmoi init jorrite
chezmoi apply
