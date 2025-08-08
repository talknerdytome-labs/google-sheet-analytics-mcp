const { execSync } = require('child_process');
const chalk = require('chalk');

class PythonDetector {
  constructor() {
    this.minVersion = '3.8.0';
    this.maxVersion = '3.13.0';
    this.pythonCommands = ['python3', 'python', 'py'];
  }

  detect() {
    console.log(chalk.blue('🔍 Detecting Python installation...'));
    
    for (const cmd of this.pythonCommands) {
      try {
        const version = this.getVersion(cmd);
        if (this.isValidVersion(version)) {
          console.log(chalk.green(`✅ Found Python ${version} at ${cmd}`));
          return { command: cmd, version };
        }
      } catch (err) {
        // Try next command
      }
    }
    
    throw new Error(`Python ${this.minVersion}+ not found`);
  }

  getVersion(command) {
    try {
      const output = execSync(`${command} --version 2>&1`, { encoding: 'utf8' });
      const match = output.match(/Python (\d+\.\d+\.\d+)/);
      return match ? match[1] : null;
    } catch (err) {
      return null;
    }
  }

  isValidVersion(version) {
    if (!version) return false;
    return this.compareVersions(version, this.minVersion) >= 0 && 
           this.compareVersions(version, this.maxVersion) < 0;
  }

  compareVersions(a, b) {
    const partsA = a.split('.').map(Number);
    const partsB = b.split('.').map(Number);
    
    for (let i = 0; i < Math.max(partsA.length, partsB.length); i++) {
      const partA = partsA[i] || 0;
      const partB = partsB[i] || 0;
      
      if (partA > partB) return 1;
      if (partA < partB) return -1;
    }
    return 0;
  }
}

module.exports = { PythonDetector };

// Run if called directly
if (require.main === module) {
  try {
    const detector = new PythonDetector();
    const result = detector.detect();
    console.log(chalk.green(`Python ${result.version} is ready!`));
  } catch (err) {
    console.error(chalk.red('Error:'), err.message);
    process.exit(1);
  }
}