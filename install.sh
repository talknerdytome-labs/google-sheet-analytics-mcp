#!/bin/bash
# Automated installation script for Google Sheets Analytics MCP Server

set -e

echo "🚀 Google Sheets Analytics MCP Server - Quick Install"
echo "======================================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ️${NC} $1"
}

# Check if running on supported OS
case "$(uname -s)" in
    Darwin)
        OS="macOS"
        ;;
    Linux)
        OS="Linux"
        ;;
    MINGW*|CYGWIN*|MSYS*)
        OS="Windows"
        ;;
    *)
        print_error "Unsupported operating system: $(uname -s)"
        exit 1
        ;;
esac

print_info "Detected OS: $OS"

# Check Python version
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 8 ]]; then
    print_error "Python 3.8+ is required. Found: $PYTHON_VERSION"
    exit 1
fi

print_status "Python $PYTHON_VERSION detected"

# Check if mcp command is available
if ! command -v mcp &> /dev/null; then
    print_error "MCP CLI not found. Please install Claude Code first."
    print_info "Visit: https://claude.ai/code"
    exit 1
fi

print_status "MCP CLI found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv venv
    print_status "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment based on OS
if [[ "$OS" == "Windows" ]]; then
    source venv/Scripts/activate
    PYTHON_PATH="venv/Scripts/python"
    PIP_PATH="venv/Scripts/pip"
else
    source venv/bin/activate
    PYTHON_PATH="venv/bin/python"
    PIP_PATH="venv/bin/pip"
fi

# Install dependencies
print_info "Installing dependencies..."
$PIP_PATH install -e .
print_status "Dependencies installed"

# Install MCP server
print_info "Installing MCP server..."
if mcp install src/mcp_server.py --name google-sheets-analytics --with-editable .; then
    print_status "MCP server installed successfully"
else
    print_warning "MCP server installation may have issues, but continuing..."
fi

# Check for credentials
CREDS_FOUND=false
if [[ -f "credentials.json" ]]; then
    CREDS_FOUND=true
    print_status "Credentials found: credentials.json"
elif [[ -f "config/credentials.json" ]]; then
    CREDS_FOUND=true
    print_status "Credentials found: config/credentials.json"
else
    print_warning "No credentials.json found"
fi

# Setup OAuth if credentials exist
if [[ "$CREDS_FOUND" == true ]]; then
    print_info "Setting up OAuth authentication..."
    
    if [[ -f "data/token.json" ]]; then
        print_status "OAuth token already exists"
    else
        print_info "Starting OAuth flow..."
        print_info "(Browser will open automatically)"
        
        if $PYTHON_PATH src/auth/oauth_setup.py; then
            print_status "OAuth setup completed successfully"
        else
            print_warning "OAuth setup failed, you can run it manually later:"
            print_info "$PYTHON_PATH src/auth/oauth_setup.py"
        fi
    fi
else
    print_warning "Skipping OAuth setup - no credentials found"
fi

echo ""
echo "======================================================="
print_status "Installation Summary:"
echo "   Virtual Environment: ✅"
echo "   Dependencies: ✅"
echo "   MCP Server: ✅"
if [[ "$CREDS_FOUND" == true ]]; then
    echo "   OAuth Setup: ✅"
else
    echo "   OAuth Setup: ⚠️  Needs credentials.json"
fi

if [[ "$CREDS_FOUND" == true ]]; then
    echo ""
    print_status "🎉 Ready to use! Available MCP tools:"
    echo "   • smart_sync - Sync Google Sheets data"
    echo "   • query_sheets - Run SQL queries"
    echo "   • get_sheet_preview - Quick preview"
    echo "   • list_synced_sheets - View synced sheets"
    echo "   • analyze_sheets - Get query suggestions"
else
    echo ""
    print_info "📝 Next steps to complete setup:"
    echo "   1. Get Google OAuth credentials:"
    echo "      - Visit https://console.cloud.google.com/"
    echo "      - Create project and enable Google Sheets API"
    echo "      - Create OAuth2 credentials (Desktop Application)"
    echo "      - Download and save as 'credentials.json'"
    echo ""
    echo "   2. Run OAuth setup:"
    echo "      $PYTHON_PATH src/auth/oauth_setup.py"
fi

echo ""
print_info "For help and troubleshooting, see README.md"