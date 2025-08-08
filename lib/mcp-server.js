const PythonBridge = require('./python-bridge');
const EventEmitter = require('events');

class MCPServer extends EventEmitter {
  constructor(options = {}) {
    super();
    this.bridge = new PythonBridge(options);
    this.initialized = false;
    this.tools = [];
  }

  async initialize() {
    await this.bridge.start();
    
    // Send initialization request
    const initResponse = await this.bridge.sendRequest('initialize', {
      protocolVersion: '0.1.0',
      capabilities: {
        tools: {},
        resources: {}
      }
    });
    
    this.serverInfo = initResponse.serverInfo;
    this.initialized = true;
    
    // Get available tools
    await this.loadTools();
    
    return initResponse;
  }

  async loadTools() {
    const response = await this.bridge.sendRequest('tools/list', {});
    this.tools = response.tools || [];
    return this.tools;
  }

  async callTool(name, arguments) {
    if (\!this.initialized) {
      throw new Error('Server not initialized');
    }
    
    const tool = this.tools.find(t => t.name === name);
    if (\!tool) {
      throw new Error(`Tool ${name} not found`);
    }
    
    const response = await this.bridge.sendRequest('tools/call', {
      name,
      arguments
    });
    
    return response;
  }

  async handleRequest(request) {
    // Route MCP protocol requests
    switch (request.method) {
      case 'initialize':
        return await this.initialize();
      
      case 'tools/list':
        return { tools: this.tools };
      
      case 'tools/call':
        return await this.callTool(
          request.params.name,
          request.params.arguments
        );
      
      default:
        throw new Error(`Unknown method: ${request.method}`);
    }
  }

  async shutdown() {
    this.bridge.stop();
    this.initialized = false;
  }
}

module.exports = MCPServer;
