#!/bin/bash

set -e

prompt_user_onepassword() {
  echo "Please open 1Password, log into all accounts, and activate 'Integrate with 1Password CLI' under Settings > CLI."
  echo "Press any key to continue..."
  read -n 1 -s -r
  echo
}

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

prompt_user_onepassword

brew install chezmoi
chezmoi init jorrite
chezmoi apply
