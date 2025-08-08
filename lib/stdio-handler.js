const readline = require('readline');

class StdioHandler {
  constructor(server) {
    this.server = server;
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false
    });
  }

  start() {
    this.rl.on('line', async (line) => {
      try {
        const request = JSON.parse(line);
        const response = await this.handleRequest(request);
        this.sendResponse(response);
      } catch (err) {
        this.sendError(err, request?.id);
      }
    });
  }

  async handleRequest(request) {
    // Validate JSON-RPC request
    if (\!request.jsonrpc || request.jsonrpc \!== '2.0') {
      throw new Error('Invalid JSON-RPC version');
    }
    
    if (\!request.method) {
      throw new Error('Method is required');
    }
    
    // Process request through MCP server
    const result = await this.server.handleRequest(request);
    
    return {
      jsonrpc: '2.0',
      id: request.id,
      result
    };
  }

  sendResponse(response) {
    process.stdout.write(JSON.stringify(response) + '\n');
  }

  sendError(error, id) {
    const errorResponse = {
      jsonrpc: '2.0',
      id: id || null,
      error: {
        code: -32603,
        message: error.message,
        data: error.stack
      }
    };
    process.stdout.write(JSON.stringify(errorResponse) + '\n');
  }

  stop() {
    this.rl.close();
  }
}

module.exports = StdioHandler;
