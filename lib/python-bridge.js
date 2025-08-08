const { PythonShell } = require('python-shell');
const path = require('path');
const fs = require('fs');
const EventEmitter = require('events');

class PythonBridge extends EventEmitter {
  constructor(options = {}) {
    super();
    this.pythonPath = this.findPython();
    this.venvPath = path.join(__dirname, '..', '.venv');
    this.serverPath = path.join(__dirname, '..', 'src', 'mcp_server.py');
    this.shell = null;
    this.isReady = false;
  }

  findPython() {
    // Check virtual environment first
    const venvPython = process.platform === 'win32'
      ? path.join(this.venvPath, 'Scripts', 'python.exe')
      : path.join(this.venvPath, 'bin', 'python');
    
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }

    // Fallback to system Python
    const which = require('which');
    try {
      return which.sync('python3') || which.sync('python');
    } catch (err) {
      throw new Error('Python not found. Please install Python 3.8+');
    }
  }

  async start() {
    const options = {
      mode: 'json',
      pythonPath: this.pythonPath,
      pythonOptions: ['-u'], // Unbuffered output
      scriptPath: path.dirname(this.serverPath),
      args: []
    };

    this.shell = new PythonShell(path.basename(this.serverPath), options);

    this.shell.on('message', (message) => {
      this.handleMessage(message);
    });

    this.shell.on('error', (err) => {
      this.emit('error', err);
    });

    return new Promise((resolve) => {
      this.once('ready', () => {
        this.isReady = true;
        resolve();
      });
    });
  }

  handleMessage(message) {
    if (message.type === 'ready') {
      this.emit('ready');
    } else {
      this.emit('message', message);
    }
  }

  async sendRequest(method, params) {
    if (\!this.isReady) {
      throw new Error('Server not ready');
    }

    const request = {
      jsonrpc: '2.0',
      id: Date.now(),
      method,
      params
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Request timeout'));
      }, 30000);

      const handler = (message) => {
        if (message.id === request.id) {
          clearTimeout(timeout);
          this.removeListener('message', handler);
          if (message.error) {
            reject(new Error(message.error.message));
          } else {
            resolve(message.result);
          }
        }
      };

      this.on('message', handler);
      this.shell.send(request);
    });
  }

  stop() {
    if (this.shell) {
      this.shell.kill();
      this.shell = null;
      this.isReady = false;
    }
  }
}

module.exports = PythonBridge;
