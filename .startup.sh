#!/bin/bash

set -e

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  ${RESET}$*"; }
log_success() { echo -e "${GREEN}✅ ${RESET}$*"; }
log_warning() { echo -e "${YELLOW}⚠️  ${RESET}$*"; }
log_error() { echo -e "${RED}❌ ${RESET}$*" >&2; }
log_step() { echo -e "\n${BOLD}${CYAN}═══ $* ═══${RESET}\n"; }
show_progress() { echo -e "${BOLD}[$1/$2]${RESET} 🔧 $3"; }

echo -e "${CYAN}${BOLD}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║        🚀  Mac Bootstrap Script  🚀                       ║
║                                                           ║
║     Setting up your Mac from scratch! ✨                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${RESET}\n"

log_info "Checking prerequisites..."
if ! ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    log_error "No network connectivity detected. Please connect to the internet and try again."
    exit 1
fi
log_success "Network connectivity confirmed"

show_progress 1 4 "Installing Xcode Command Line Tools"
if xcode-select -p >/dev/null 2>&1; then
    log_success "Xcode Command Line Tools already installed"
else
    log_info "Installing Xcode Command Line Tools..."
    xcode-select --install 2>/dev/null || true
    log_info "Please complete the Xcode installation in the popup window"
    log_info "Press any key after installation completes..."
    read -n 1 -s -r < /dev/tty
    echo

    if xcode-select -p >/dev/null 2>&1; then
        log_success "Xcode Command Line Tools installed successfully"
    else
        log_error "Xcode Command Line Tools installation failed"
        exit 1
    fi
fi

show_progress 2 4 "Installing Homebrew"
if command -v brew >/dev/null 2>&1; then
    log_success "Homebrew is already installed"
else
    log_info "Installing Homebrew..."

    max_attempts=3
    attempt=1
    while [ $attempt -le $max_attempts ]; do
        if install_script="$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && [ -n "$install_script" ] && /bin/bash -c "$install_script"; then
            log_success "Homebrew installed successfully"
            break
        else
            if [ $attempt -lt $max_attempts ]; then
                log_warning "Homebrew installation failed. Retrying (${attempt}/${max_attempts})..."
                sleep 5
            else
                log_error "Homebrew installation failed after ${max_attempts} attempts"
                exit 1
            fi
        fi
        attempt=$((attempt + 1))
    done

    log_info "Configuring Homebrew environment..."
    if [ -f "$HOME/.zprofile" ]; then
        if ! grep -q '/opt/homebrew/bin/brew shellenv' "$HOME/.zprofile"; then
            (
                echo
                echo '# Homebrew'
                echo 'eval "$(/opt/homebrew/bin/brew shellenv)"'
            ) >> "$HOME/.zprofile"
        fi
    else
        (
            echo
            echo '# Homebrew'
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"'
        ) >> "$HOME/.zprofile"
    fi

    eval "$(/opt/homebrew/bin/brew shellenv)"

    if command -v brew >/dev/null 2>&1; then
        log_success "Homebrew configured and ready"
    else
        log_error "Homebrew configuration failed"
        exit 1
    fi
fi

show_progress 3 4 "Installing 1Password and CLI"
if command -v op >/dev/null 2>&1; then
    log_success "1Password and 1Password CLI already installed"
else
    log_info "Installing 1Password and 1Password CLI..."

    max_attempts=3
    attempt=1
    while [ $attempt -le $max_attempts ]; do
        if brew install --cask 1password && brew install --cask 1password-cli; then
            log_success "1Password installed successfully"
            break
        else
            if [ $attempt -lt $max_attempts ]; then
                log_warning "Installation failed. Retrying (${attempt}/${max_attempts})..."
                sleep 3
            else
                log_error "1Password installation failed after ${max_attempts} attempts"
                exit 1
            fi
        fi
        attempt=$((attempt + 1))
    done
fi

log_step "1Password Setup Required"
echo -e "${BOLD}Please complete the following steps in 1Password:${RESET}"
echo -e "  ${CYAN}1.${RESET} Log into all your accounts"
echo -e "  ${CYAN}2.${RESET} Go to Settings → Developer → CLI"
echo -e "     ${YELLOW}➜${RESET} Enable 'Integrate with 1Password CLI'"
echo -e "  ${CYAN}3.${RESET} Go to Settings → Developer → SSH Agent"
echo -e "     ${YELLOW}➜${RESET} Enable 'Use the SSH agent'"
echo
log_info "Press any key after completing these steps..."
read -n 1 -s -r < /dev/tty
echo

log_info "Verifying 1Password CLI integration..."
max_attempts=3
attempt=1
while [ $attempt -le $max_attempts ]; do
    if op signin >/dev/null 2>&1 || op account list >/dev/null 2>&1; then
        log_success "1Password CLI is configured correctly"
        break
    else
        if [ $attempt -lt $max_attempts ]; then
            log_warning "1Password CLI not ready. Please ensure CLI integration is enabled."
            log_info "Press any key to retry..."
            read -n 1 -s -r < /dev/tty
            echo
        else
            log_error "1Password CLI verification failed. Please check your settings."
            exit 1
        fi
    fi
    attempt=$((attempt + 1))
done

show_progress 4 4 "Installing and initializing Chezmoi"
if command -v chezmoi >/dev/null 2>&1; then
    log_success "Chezmoi already installed"
else
    log_info "Installing Chezmoi..."
    if brew install chezmoi; then
        log_success "Chezmoi installed successfully"
    else
        log_error "Chezmoi installation failed"
        exit 1
    fi
fi

AGE_DIR="$HOME/.config/age"
AGE_KEY_FILE="$AGE_DIR/key.txt"
OP_ITEM="op://afcfz2u36qbb4w5iikx4aol2z4/ab73kbvbmhh5xnyn75p7oquloy/key.txt"

echo "🔐 Bootstrapping age key..."

if ! command -v op >/dev/null 2>&1; then
  log_error "❌ 1Password CLI (op) not installed"
  exit 1
fi

if ! op account list >/dev/null 2>&1; then
  log_error "❌ Not signed into 1Password CLI"
  echo "➡️  Run: op signin"
  exit 1
fi

mkdir -p "$AGE_DIR"
chmod 700 "$AGE_DIR"

if [[ -f "$AGE_KEY_FILE" ]]; then
  log_info "✔ age key already exists, skipping"
  exit 0
fi

op read "$OP_ITEM" >"$AGE_KEY_FILE"

chmod 600 "$AGE_KEY_FILE"

log_success "✅ age key installed"

log_info "Initializing Chezmoi from repository..."
if chezmoi init jorrite; then
    log_success "Chezmoi initialized successfully"
else
    log_error "Chezmoi initialization failed"
    exit 1
fi

log_info "Applying Chezmoi configuration..."
if chezmoi apply; then
    log_success "Chezmoi configuration applied successfully"
else
    log_warning "Chezmoi apply had some issues, but continuing..."
fi
