#!/bin/bash
# Chezmoi helper library for common functions

# Color definitions
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  ${RESET}$*"
}

log_success() {
    echo -e "${GREEN}✅ ${RESET}$*"
}

log_warning() {
    echo -e "${YELLOW}⚠️  ${RESET}$*"
}

log_error() {
    echo -e "${RED}❌ ${RESET}$*" >&2
}

log_step() {
    echo -e "\n${BOLD}${CYAN}$*${RESET}"
}

log_substep() {
    echo -e "${MAGENTA}  ➜ ${RESET}$*"
}

# Progress indicator
show_progress() {
    local current=$1
    local total=$2
    local task=$3
    echo -e "${BOLD}[${current}/${total}]${RESET} 🔧 ${task}"
}

# Banner display
show_banner() {
    echo -e "${CYAN}${BOLD}"
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║        🚀  Welcome to Chezmoi Setup  🚀                   ║
║                                                           ║
║     Let's get your Mac configured perfectly! ✨           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
    echo -e "${RESET}\n"
}

# Celebration banner
show_celebration() {
    echo -e "\n${GREEN}${BOLD}"
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🎉  Setup Complete!  🎉                         ║
║                                                           ║
║     Your Mac is now configured and ready to use! 🚀       ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
    echo -e "${RESET}\n"
}

# Retry logic with exponential backoff
retry_with_backoff() {
    local max_attempts="${1}"
    local delay="${2}"
    local max_delay="${3:-300}"
    shift 3
    local attempt=1
    local exit_code=0

    while [ $attempt -le $max_attempts ]; do
        if [ $attempt -gt 1 ]; then
            log_warning "Attempt ${attempt}/${max_attempts}..."
        fi

        if "$@"; then
            return 0
        else
            exit_code=$?
        fi

        if [ $attempt -lt $max_attempts ]; then
            log_warning "Command failed. Retrying in ${delay}s..."
            sleep "$delay"
            delay=$((delay * 2))
            if [ $delay -gt $max_delay ]; then
                delay=$max_delay
            fi
        fi

        attempt=$((attempt + 1))
    done

    log_error "Command failed after ${max_attempts} attempts"
    return $exit_code
}

# Check network connectivity
check_network() {
    log_substep "Checking network connectivity..."
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        log_success "Network is available"
        return 0
    else
        log_error "No network connectivity detected"
        return 1
    fi
}

# Validate command exists
require_command() {
    local cmd=$1
    local install_hint=$2

    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "Required command '$cmd' is not available"
        if [ -n "$install_hint" ]; then
            log_info "$install_hint"
        fi
        return 1
    fi
    return 0
}

# Safe file operation with backup
safe_append_file() {
    local file=$1
    local content=$2
    local backup="${file}.backup.$(date +%s)"

    if [ -f "$file" ]; then
        cp "$file" "$backup"
        log_substep "Created backup: $backup"
    fi

    echo "$content" >> "$file"
}

# Check if running in a virtual machine
is_virtual_machine() {
    sysctl -n machdep.cpu.brand_string | grep -qi "Virtual"
}

# Validate successful installation
validate_brew_package() {
    local package=$1
    if brew list "$package" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Spinner for long-running operations
spinner() {
    local pid=$1
    local task=$2
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0

    echo -n "  "
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) % 10 ))
        printf "\r  ${CYAN}${spin:$i:1}${RESET} $task"
        sleep 0.1
    done
    printf "\r"
}

# Confirm action
confirm() {
    local prompt=$1
    local default=${2:-n}

    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n] "
    else
        prompt="$prompt [y/N] "
    fi

    read -r -p "$prompt" response
    response=${response:-$default}

    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Timer functions
start_timer() {
    TIMER_START=$(date +%s)
}

end_timer() {
    local end=$(date +%s)
    local duration=$((end - TIMER_START))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    if [ $minutes -gt 0 ]; then
        echo "⏱️  Completed in ${minutes}m ${seconds}s"
    else
        echo "⏱️  Completed in ${seconds}s"
    fi
}
