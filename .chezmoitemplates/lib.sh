#!/bin/bash
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

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

show_progress() {
    local current=$1
    local total=$2
    local task=$3
    echo -e "${BOLD}[${current}/${total}]${RESET} 🔧 ${task}"
}

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

is_virtual_machine() {
    sysctl -n machdep.cpu.brand_string | grep -qi "Virtual"
}

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
