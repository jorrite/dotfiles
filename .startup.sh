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

echo "Please open 1Password and: "
echo "- Log into all accounts"
echo "- Activate Integrate with 1Password CLI under Developer>CLI"
echo "- Enable the 1Password SSH agent under Developer>SSH-agent "
read -n 1 -s -r < /dev/tty
echo

op signin
brew install chezmoi
chezmoi init jorrite
chezmoi apply
