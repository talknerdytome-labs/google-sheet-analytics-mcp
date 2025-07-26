#!/bin/bash
# Post-clone setup script for Google Sheets Analytics MCP
# Run this after git clone to complete setup

echo "🚀 GOOGLE SHEETS ANALYTICS MCP - POST-CLONE SETUP"
echo "=================================================="

# Check if credentials.json exists
if [ ! -f "credentials.json" ]; then
    echo "❌ credentials.json not found!"
    echo ""
    echo "📋 Please follow these steps first:"
    echo "1. Go to Google Cloud Console: https://console.cloud.google.com/"
    echo "2. Create OAuth2 credentials (Desktop application)"
    echo "3. Download as 'credentials.json' in this directory"
    echo "4. Run this script again: ./post-clone.sh"
    exit 1
fi

# Run Python setup
echo "🔧 Running automated setup..."
python3 setup.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Setup complete!"
    echo "✅ Ready to use with Claude Desktop"
else
    echo ""
    echo "❌ Setup failed. Check errors above."
    exit 1
fi