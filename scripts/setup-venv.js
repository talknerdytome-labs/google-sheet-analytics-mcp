const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const chalk = require('chalk');

class VenvSetup {
  constructor() {
    this.venvPath = path.join(__dirname, '..', '.venv');
    this.requirementsPath = path.join(__dirname, '..', 'requirements.txt');
  }

  async setup() {
    console.log(chalk.blue('🚀 Setting up Python environment...'));
    
    // Check if venv exists
    if (this.venvExists()) {
      console.log(chalk.yellow('⚠️  Virtual environment already exists'));
      const isValid = await this.validateVenv();
      if (\!isValid) {
        console.log(chalk.yellow('Virtual environment is invalid, recreating...'));
        await this.removeVenv();
        await this.createVenv();
      }
    } else {
      await this.createVenv();
    }
    
    await this.installDependencies();
    await this.validateInstallation();
  }

  venvExists() {
    return fs.existsSync(this.venvPath);
  }

  async validateVenv() {
    try {
      const pythonPath = this.getPythonPath();
      execSync(`"${pythonPath}" -c "import sys; print(sys.version)"`, { 
        encoding: 'utf8',
        stdio: 'ignore'
      });
      return true;
    } catch (err) {
      return false;
    }
  }

  async removeVenv() {
    console.log(chalk.yellow('Removing old virtual environment...'));
    try {
      if (process.platform === 'win32') {
        execSync(`rmdir /s /q "${this.venvPath}"`, { shell: true, stdio: 'ignore' });
      } else {
        execSync(`rm -rf "${this.venvPath}"`, { stdio: 'ignore' });
      }
      console.log(chalk.green('✅ Old virtual environment removed'));
    } catch (err) {
      console.log(chalk.red('❌ Failed to remove old virtual environment'));
      throw err;
    }
  }

  async createVenv() {
    console.log(chalk.blue('Creating virtual environment...'));
    try {
      const { PythonDetector } = require('./check-python');
      const { command } = new PythonDetector().detect();
      
      execSync(`"${command}" -m venv "${this.venvPath}"`, {
        encoding: 'utf8',
        stdio: 'ignore'
      });
      
      console.log(chalk.green('✅ Virtual environment created'));
    } catch (err) {
      console.log(chalk.red('❌ Failed to create virtual environment'));
      throw err;
    }
  }

  async installDependencies() {
    console.log(chalk.blue('Installing Python dependencies...'));
    try {
      const pipPath = this.getPipPath();
      
      // Upgrade pip first
      execSync(`"${pipPath}" install --upgrade pip`, {
        encoding: 'utf8',
        stdio: 'ignore'
      });
      
      // Install requirements
      if (fs.existsSync(this.requirementsPath)) {
        execSync(`"${pipPath}" install -r "${this.requirementsPath}"`, {
          encoding: 'utf8',
          stdio: 'ignore'
        });
      }
      
      console.log(chalk.green('✅ Dependencies installed'));
    } catch (err) {
      console.log(chalk.red('❌ Failed to install dependencies'));
      throw err;
    }
  }

  async validateInstallation() {
    console.log(chalk.blue('Validating installation...'));
    try {
      const pythonPath = this.getPythonPath();
      
      // Test critical imports
      const testCode = `
import sys
import json
import asyncio
import sqlite3
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    print("All imports successful")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)
`;
      
      execSync(`"${pythonPath}" -c "${testCode}"`, {
        encoding: 'utf8',
        stdio: 'ignore'
      });
      
      console.log(chalk.green('✅ Installation validated'));
    } catch (err) {
      console.log(chalk.yellow('⚠️  Installation validation had issues (but continuing)'));
    }
  }

  getPythonPath() {
    return process.platform === 'win32'
      ? path.join(this.venvPath, 'Scripts', 'python.exe')
      : path.join(this.venvPath, 'bin', 'python');
  }

  getPipPath() {
    return process.platform === 'win32'
      ? path.join(this.venvPath, 'Scripts', 'pip.exe')
      : path.join(this.venvPath, 'bin', 'pip');
  }
}

module.exports = { VenvSetup };

// Run if called directly
if (require.main === module) {
  const setup = new VenvSetup();
  setup.setup().catch(err => {
    console.error(chalk.red('Setup failed:'), err.message);
    process.exit(1);
  });
}
