const chalk = require('chalk');
const path = require('path');
const fs = require('fs');

async function postinstall() {
  console.log(chalk.bold.blue('\n📦 Google Sheets MCP Server - Post Install Setup\n'));
  
  try {
    // Step 1: Check Python
    const { PythonDetector } = require('./check-python');
    const detector = new PythonDetector();
    const pythonInfo = detector.detect();
    
    // Step 2: Setup virtual environment
    const { VenvSetup } = require('./setup-venv');
    const venvSetup = new VenvSetup();
    await venvSetup.setup();
    
    // Step 3: Check for credentials
    checkCredentials();
    
    // Step 4: Show success message
    showSuccessMessage();
    
  } catch (err) {
    console.error(chalk.red('\n❌ Setup failed:'), err.message);
    console.log(chalk.yellow('\nPlease run: npm run setup'));
    // Don't exit with error on postinstall - let user fix manually
  }
}

function checkCredentials() {
  const credentialsPath = path.join(__dirname, '..', 'config', 'credentials.json');
  
  if (!fs.existsSync(credentialsPath)) {
    console.log(chalk.yellow('\n⚠️  OAuth credentials not found'));
    console.log(chalk.white('Please follow these steps:'));
    console.log('1. Go to https://console.cloud.google.com');
    console.log('2. Create a new project or select existing');
    console.log('3. Enable Google Sheets API');
    console.log('4. Create OAuth 2.0 credentials');
    console.log('5. Download and save as config/credentials.json');
  } else {
    console.log(chalk.green('✅ OAuth credentials found'));
  }
}

function showSuccessMessage() {
  console.log(chalk.green.bold('\n✨ Setup complete!\n'));
  console.log('To configure with Claude Desktop, add to your config:');
  console.log(chalk.cyan(`
{
  "mcpServers": {
    "google-sheets": {
      "command": "npx",
      "args": ["@tntm/google-sheets-mcp"]
    }
  }
}
`));
  console.log('For local development, run:');
  console.log(chalk.cyan('  npm start\n'));
}

// Run if called directly
if (require.main === module) {
  postinstall().catch(console.error);
}

module.exports = postinstall;