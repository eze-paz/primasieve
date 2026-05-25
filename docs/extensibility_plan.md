# Sandpie Extensibility Plan

**Date:** 2025-01-XX  
**Status:** Planning Phase  
**Goal:** Make sandpie maintainable and extensible for future development

---

## Current Architecture Analysis

### File Structure
```
projects/sandpie/
├── sandpie.html              (6,153 lines) - Main UI + inline scripts
├── sandpie.js                (861 lines)   - Service Worker (agent loop, tools)
├── sandpie-service.js        (443 lines)   - Node.js server (proxy, shell)
├── sandpie-webllm.html       (variant)
├── sandpie-wllama.html       (variant)
├── variants/
│   └── sandpie-lightweight.html
└── modules/
    ├── images.js             (254 lines)   - Image handling (extracted module)
    ├── webllm.js             (variant module)
    └── EXTRACTION_SUMMARY.md
```

### Key Architectural Patterns

#### 1. Service Worker (sandpie.js)
- **Single monolithic file** with all tool implementations
- **Tool registry**: Hardcoded `switch` statement in `runTool()`
- **Tools**: `run_python`, `fetch_file`, `show_artifact`, `load_image`
- **Agent loop**: `runAgent()` → `streamOneRound()` → `runTool()` → repeat
- **Pyodide**: Single shared interpreter (trade-off for simplicity)

#### 2. Main UI (sandpie.html)
- **6,153 lines** of HTML + CSS + inline JavaScript
- **210+ functions** defined globally
- **State**: Scattered global variables (`_providers`, `activeConvId`, `convStreams`)
- **Event handling**: Inline `onclick` attributes mixed with `addEventListener`
- **One module extracted**: `SandpieImages` (good pattern to follow)

#### 3. Module Pattern (images.js - Reference Implementation)
```javascript
const SandpieImages = (function() {
  'use strict';

  // Private state
  let _attachedImage = null;

  // Private helpers
  function compressImage(img, maxDim, quality) { ... }

  // Public API
  return {
    init,
    handleSelect: handleImageSelect,
    clear,
    saveToOpfs,
    dataUrlFromPath,
    compressForLLM,
    buildContent,
    hasImage,
    getState,
    setState
  };
})();
```

---

## Extensibility Problems

### Critical Issues

1. **Tool Registration is Hardcoded**
   - Adding a new tool requires editing `runTool()` switch statement
   - No plugin system or dynamic registration
   - Tools are tightly coupled to the SW

2. **Monolithic UI File**
   - 6,153 lines is difficult to navigate and maintain
   - Mixed concerns: UI rendering, state management, event handling, API calls
   - No clear separation between layers

3. **Global State Pollution**
   - 210+ global functions
   - State scattered across multiple global variables
   - Risk of naming conflicts and hard-to-track bugs

4. **No Configuration Layer**
   - Hardcoded values throughout (e.g., `RETRYABLE_STATUS`, endpoints)
   - No centralized configuration management
   - Environment-specific values mixed with code

5. **Tight Coupling**
   - UI directly calls SW endpoints
   - SW directly implements tools
   - No abstraction layers for swapping implementations

6. **Limited Testing Surface**
   - Most code is inline in HTML (not testable)
   - No dependency injection
   - Hard to mock external dependencies

---

## Proposed Extensibility Architecture

### Phase 1: Plugin System for Tools (High Impact)

**Goal**: Enable dynamic tool registration without editing core SW code

#### Design
```javascript
// sandpie.js - Tool Registry
class ToolRegistry {
  constructor() {
    this._tools = new Map();
    this._hooks = new Map();
  }

  register(name, handler, metadata = {}) {
    this._tools.set(name, {
      handler,
      metadata: {
        name,
        description: metadata.description || '',
        params: metadata.params || {},
        ...metadata
      }
    });
  }

  async execute(name, args, ctx) {
    const tool = this._tools.get(name);
    if (!tool) throw new Error(`Unknown tool: ${name}`);
    return await tool.handler(args, ctx);
  }

  list() {
    return Array.from(this._tools.values()).map(t => t.metadata);
  }

  on(event, callback) {
    if (!this._hooks.has(event)) this._hooks.set(event, []);
    this._hooks.get(event).push(callback);
  }

  async emit(event, data) {
    const callbacks = this._hooks.get(event) || [];
    for (const cb of callbacks) await cb(data);
  }
}

const toolRegistry = new ToolRegistry();

// Built-in tools
toolRegistry.register('run_python', tool_run_python, {
  description: 'Execute Python code in Pyodide',
  params: { code: 'string', path: 'string?', args: 'array?' }
});

toolRegistry.register('fetch_file', tool_fetch_file, {
  description: 'Download file from Dropbox',
  params: { path: 'string' }
});

// Plugin loading (future)
async function loadToolPlugins() {
  // Could load from OPFS, remote URL, or inline config
  const pluginConfigs = await loadToolConfigs();
  for (const config of pluginConfigs) {
    const handler = await loadToolHandler(config.url);
    toolRegistry.register(config.name, handler, config.metadata);
  }
}
```

**Benefits**:
- Add tools without editing `sandpie.js`
- Tools can be loaded from external files
- Self-documenting tool metadata
- Hook system for cross-cutting concerns (logging, auth, rate limiting)

---

### Phase 2: Modular UI Architecture (High Impact)

**Goal**: Break down 6,153-line HTML into focused modules

#### Proposed Module Structure
```
projects/sandpie/modules/
├── core/
│   ├── state.js           # Centralized state management
│   ├── events.js          # Event bus
│   └── config.js          # Configuration management
├── ui/
│   ├── messages.js        # Message rendering
│   ├── providers.js       # Provider management UI
│   ├── artifacts.js       # Artifact panel
│   └── themes.js          # Theme management
├── api/
│   ├── agent.js           # Agent API calls
│   ├── storage.js         # OPFS / Dropbox operations
│   └── proxy.js           # Proxy requests
├── tools/
│   ├── python.js          # Python tool UI helpers
│   └── images.js          # (already exists)
└── index.js               # Module loader / initialization
```

#### Module Pattern (Standardized)
```javascript
// modules/core/state.js
const SandpieState = (function() {
  'use strict';

  // Private state
  const _state = {
    activeConvId: null,
    providers: [],
    conversations: new Map(),
    settings: {}
  };

  // Private event emitter
  const _emitter = new EventTarget();

  // Public API
  return {
    get(key) {
      return _state[key];
    },

    set(key, value) {
      const oldValue = _state[key];
      _state[key] = value;
      _emitter.dispatchEvent(new CustomEvent('change', {
        detail: { key, oldValue, newValue: value }
      }));
      this.persist();
    },

    subscribe(key, callback) {
      _emitter.addEventListener('change', (e) => {
        if (e.detail.key === key) callback(e.detail.newValue, e.detail.oldValue);
      });
    },

    persist() {
      localStorage.setItem('sandpie-state', JSON.stringify({
        activeConvId: _state.activeConvId,
        providers: _state.providers,
        settings: _state.settings
      }));
    },

    restore() {
      const saved = localStorage.getItem('sandpie-state');
      if (saved) {
        const data = JSON.parse(saved);
        Object.assign(_state, data);
      }
    },

    init() {
      this.restore();
    }
  };
})();
```

#### Module Loader
```javascript
// modules/index.js
const SandpieModules = {
  core: {},
  ui: {},
  api: {},
  tools: {},

  async load() {
    // Load order matters - core first
    await this.loadCore();
    await this.loadAPI();
    await this.loadUI();
    await this.loadTools();

    // Initialize all modules
    for (const group of Object.values(this)) {
      for (const module of Object.values(group)) {
        if (module.init) await module.init();
      }
    }
  },

  async loadCore() {
    this.core.state = SandpieState;
    this.core.events = SandpieEvents;
    this.core.config = SandpieConfig;
  },

  // ... other loaders
};

// Auto-initialize
document.addEventListener('DOMContentLoaded', () => SandpieModules.load());
```

**Benefits**:
- Clear separation of concerns
- Each module is testable in isolation
- Easy to locate and modify specific functionality
- Reduced cognitive load when navigating code

---

### Phase 3: Configuration Layer (Medium Impact)

**Goal**: Centralize all configuration values

#### Design
```javascript
// modules/core/config.js
const SandpieConfig = (function() {
  'use strict';

  const DEFAULTS = {
    // API endpoints
    endpoints: {
      agent: '/sandpie-agent',
      stream: '/sandpie-stream',
      python: '/sandpie-py',
      opfs: '/opfs/'
    },

    // Retry behavior
    retry: {
      maxAttempts: 3,
      backoffMs: 1000,
      retryableStatus: [408, 425, 429, 500, 502, 503, 504, 520, 522, 524]
    },

    // UI defaults
    ui: {
      theme: 'dark',
      maxMessages: 100,
      autoScroll: true
    },

    // Storage
    storage: {
      convDir: '_conversations',
      maxConvSize: 10 * 1024 * 1024  // 10MB
    },

    // Tool defaults
    tools: {
      pythonTimeout: 30000,
      imageMaxDim: 1024,
      imageQuality: 0.85
    }
  };

  let _config = { ...DEFAULTS };

  return {
    get(path) {
      return path.split('.').reduce((obj, key) => obj?.[key], _config);
    },

    set(path, value) {
      const keys = path.split('.');
      const last = keys.pop();
      const target = keys.reduce((obj, key) => obj[key], _config);
      target[last] = value;
    },

    merge(partial) {
      _config = deepMerge(_config, partial);
    },

    reset() {
      _config = { ...DEFAULTS };
    },

    loadFromUser() {
      const userConfig = localStorage.getItem('sandpie-config');
      if (userConfig) {
        this.merge(JSON.parse(userConfig));
      }
    }
  };
})();
```

**Benefits**:
- Single source of truth for configuration
- Easy to override for different environments
- User-customizable settings
- No more hunting for hardcoded values

---

### Phase 4: Dependency Injection & Testing (Medium Impact)

**Goal**: Enable testing and swapping implementations

#### Design
```javascript
// modules/core/container.js
const SandpieContainer = (function() {
  'use strict';

  const _services = new Map();
  const _factories = new Map();

  return {
    register(name, factory) {
      _factories.set(name, factory);
    },

    get(name) {
      if (_services.has(name)) {
        return _services.get(name);
      }

      const factory = _factories.get(name);
      if (!factory) throw new Error(`Service not found: ${name}`);

      const instance = factory(this);
      _services.set(name, instance);
      return instance;
    },

    mock(name, instance) {
      _services.set(name, instance);
    },

    clear() {
      _services.clear();
    }
  };
})();

// Register services
SandpieContainer.register('state', () => SandpieState);
SandpieContainer.register('config', () => SandpieConfig);
SandpieContainer.register('api', (c) => SandpieAPI(c.get('config')));
SandpieContainer.register('storage', (c) => SandpieStorage(c.get('config')));

// Usage in modules
const state = SandpieContainer.get('state');
const api = SandpieContainer.get('api');

// Testing
SandpieContainer.mock('storage', new MockStorage());
```

**Benefits**:
- Easy to mock dependencies for testing
- Swappable implementations (e.g., different storage backends)
- Clear dependency graph
- Enables unit testing of individual modules

---

### Phase 5: Event-Driven Architecture (Low Impact)

**Goal**: Decouple components via events

#### Design
```javascript
// modules/core/events.js
const SandpieEvents = (function() {
  'use strict';

  const emitter = new EventTarget();

  return {
    on(event, callback) {
      emitter.addEventListener(event, callback);
    },

    off(event, callback) {
      emitter.removeEventListener(event, callback);
    },

    async emit(event, detail) {
      const e = new CustomEvent(event, { detail, cancelable: true });
      emitter.dispatchEvent(e);
      return !e.defaultPrevented;
    },

    once(event, callback) {
      const wrapper = (e) => {
        callback(e);
        this.off(event, wrapper);
      };
      this.on(event, wrapper);
    }
  };
})();

// Usage examples
SandpieEvents.on('message:sent', (msg) => {
  console.log('Message sent:', msg);
});

SandpieEvents.on('tool:started', (tool) => {
  showToolIndicator(tool.name);
});

SandpieEvents.on('tool:completed', (result) => {
  hideToolIndicator();
});
```

**Benefits**:
- Loose coupling between modules
- Easy to add cross-cutting features (logging, analytics)
- No circular dependencies
- Clear communication patterns

---

## Migration Roadmap

### Iteration 1: Foundation (Week 1-2)
- [ ] Create `modules/core/` directory
- [ ] Implement `SandpieConfig` module
- [ ] Implement `SandpieEvents` module
- [ ] Implement `SandpieState` module (partial)
- [ ] Update `sandpie.html` to load core modules
- [ ] Migrate 3-5 global state usages to `SandpieState`

### Iteration 2: Tool Plugin System (Week 2-3)
- [ ] Implement `ToolRegistry` in `sandpie.js`
- [ ] Migrate existing tools to registry
- [ ] Update `runTool()` to use registry
- [ ] Add tool metadata schema
- [ ] Document tool registration API

### Iteration 3: UI Modules - Messages (Week 3-4)
- [ ] Create `modules/ui/messages.js`
- [ ] Extract message rendering functions
- [ ] Extract message event handlers
- [ ] Update `sandpie.html` to use module
- [ ] Test message flow end-to-end

### Iteration 4: UI Modules - Providers (Week 4)
- [ ] Create `modules/ui/providers.js`
- [ ] Extract provider management functions
- [ ] Extract provider UI rendering
- [ ] Update `sandpie.html` to use module
- [ ] Test provider CRUD operations

### Iteration 5: UI Modules - Artifacts (Week 5)
- [ ] Create `modules/ui/artifacts.js`
- [ ] Extract artifact panel functions
- [ ] Extract artifact rendering
- [ ] Update `sandpie.html` to use module
- [ ] Test artifact display/interaction

### Iteration 6: API Layer (Week 5-6)
- [ ] Create `modules/api/agent.js`
- [ ] Create `modules/api/storage.js`
- [ ] Extract API calls from inline scripts
- [ ] Update modules to use API layer
- [ ] Test all API interactions

### Iteration 7: Dependency Injection (Week 6)
- [ ] Implement `SandpieContainer`
- [ ] Register core services
- [ ] Update modules to use container
- [ ] Add mocking support for testing

### Iteration 8: Cleanup & Documentation (Week 7)
- [ ] Remove dead code from `sandpie.html`
- [ ] Update inline event handlers to use modules
- [ ] Write module documentation
- [ ] Create extensibility guide for contributors
- [ ] Add examples: custom tool, custom module

---

## Success Metrics

### Code Quality
- [ ] `sandpie.html` reduced from 6,153 to <2,000 lines
- [ ] Zero global functions (all namespaced)
- [ ] All configuration centralized
- [ ] Tool registration is dynamic (no hardcoded switch)

### Maintainability
- [ ] Adding a new tool requires <50 lines of code
- [ ] Adding a new UI module requires no changes to existing modules
- [ ] Each module has <300 lines
- [ ] Clear dependency graph

### Extensibility
- [ ] Tools can be loaded from external files
- [ ] Modules can be added without touching core files
- [ ] Configuration can be overridden per-environment
- [ ] Services can be mocked for testing

### Developer Experience
- [ ] Clear onboarding documentation
- [ ] Examples for common extension patterns
- [ ] TypeScript definitions (optional)
- [ ] Linting/formatting rules

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking changes during migration | High | Incremental migration, maintain backward compatibility layer |
| Performance regression | Medium | Benchmark before/after, lazy-load modules |
| Increased complexity | Medium | Clear patterns, documentation, code reviews |
| Testing burden | Low | Start with DI, add tests gradually |
| Browser compatibility | Low | Use standard APIs (EventTarget, CustomEvent) |

---

## Open Questions

1. **TypeScript**: Should we migrate to TypeScript for better type safety?
2. **Build Step**: Is a bundler (esbuild, rollup) acceptable, or must we stay zero-build?
3. **Tool Distribution**: How should external tools be distributed? (OPFS, CDN, git)
4. **State Persistence**: Should we use IndexedDB instead of localStorage for larger datasets?
5. **Backward Compatibility**: How long to maintain the old API during migration?

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** based on immediate needs
3. **Create a proof-of-concept** for the tool plugin system
4. **Set up branching strategy** for incremental migration
5. **Define testing approach** (unit tests, integration tests, E2E)

---

**Appendix: Code Examples**

See `projects/sandpie/modules/EXTRACTION_SUMMARY.md` for a real example of extracting the `images.js` module.
