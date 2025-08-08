const { PythonShell } = require('python-shell');
const path = require('path');
const EventEmitter = require('events');

class GoogleSheetsMCPServer extends EventEmitter {
  constructor(options = {}) {
    super();
    this.options = {
      pythonPath: this._getPythonPath(),
      scriptPath: path.join(__dirname, 'src'),
      ...options
    };
    this.shell = null;
  }

  _getPythonPath() {
    const venvPath = path.join(__dirname, '.venv');
    return process.platform === 'win32'
      ? path.join(venvPath, 'Scripts', 'python.exe')
      : path.join(venvPath, 'bin', 'python');
  }

  async start() {
    return new Promise((resolve, reject) => {
      this.shell = new PythonShell('mcp_server.py', this.options);
      
      this.shell.on('message', (message) => {
        this.emit('message', message);
      });
      
      this.shell.on('error', (err) => {
        this.emit('error', err);
        reject(err);
      });
      
      this.shell.on('pythonError', (err) => {
        this.emit('error', err);
        reject(err);
      });
      
      // Server started successfully
      setTimeout(() => resolve(this), 100);
    });
  }

  async stop() {
    if (this.shell) {
      this.shell.kill();
      this.shell = null;
    }
  }

  async sendMessage(message) {
    if (!this.shell) {
      throw new Error('Server not started');
    }
    this.shell.send(message);
  }
}

module.exports = GoogleSheetsMCPServer;

// If run directly, start the server
if (require.main === module) {
  const server = new GoogleSheetsMCPServer();
  server.start().catch(console.error);
}