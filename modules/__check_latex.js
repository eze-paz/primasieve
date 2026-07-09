(() => {
  'use strict';

  const BUSYTEX_BASE = 'https://busytex.github.io/dist/';

  const $path    = document.getElementById('projectPath');
  const $tree    = document.getElementById('filetree');
  const $actions = document.getElementById('actions');
  const $btn     = document.getElementById('compileBtn');
  const $clear   = document.getElementById('clearBtn');
  const $status  = document.getElementById('status');
  const $log     = document.getElementById('logpanel');
  const $stage1  = document.getElementById('stage1');
  const $stage2  = document.getElementById('stage2');
  const $result  = document.getElementById('result');
  const $progBar = document.getElementById('progressBar');
  const $progFill = document.getElementById('progressFill');

  let fileMap    = {};
  let masterFile = '';
  let worker     = null;

  const setStatus = (msg, cls) => { $status.textContent = msg; $status.className = cls || ''; };
  const logAppend = (txt) => { $log.textContent += txt + '\n'; $log.classList.add('visible'); };
  const setProgress = (pct) => { $progFill.style.width = Math.min(100, Math.max(0, pct)) + '%'; };

  // ===== OPFS helpers =====
  async function getDb() {
    return await navigator.storage.getDirectory();
  }

  async function resolveDir(parts) {
    let dir = await getDb();
    for (const p of parts) {
      dir = await dir.getDirectoryHandle(p, { create: false });
    }
    return dir;
  }

  async function walkDir(dir, prefix, out) {
    for await (const [name, handle] of dir.entries()) {
      const full = prefix ? prefix + '/' + name : name;
      if (handle.kind === 'directory') {
        out.dirs.push(full);
        if (name === 'node_modules' || name === '.git' || name.startsWith('.')) continue;
        await walkDir(handle, full, out);
      } else {
        out.files.push(full);
        if (name.endsWith('.tex')) out.texFiles.push(full);
      }
    }
  }

  async function readFileBytes(path) {
    const parts = path.split('/');
    const name = parts.pop();
    const dir = await resolveDir(parts);
    const fh = await dir.getFileHandle(name);
    const f = await fh.getFile();
    return new Uint8Array(await f.arrayBuffer());
  }

  // ===== Project loading =====
  async function loadProject(projectPath) {
    if (!projectPath) { setStatus('No project specified.', 'err'); return; }
    fileMap = {};
    masterFile = '';
    $path.textContent = '/' + projectPath;
    setStatus('Scanning project…');
    $progBar.classList.remove('visible');
    $log.textContent = ''; $log.classList.remove('visible');

    try {
      const rootDir = await resolveDir(projectPath.split('/').filter(Boolean));
      const out = { files: [], dirs: [], texFiles: [] };
      await walkDir(rootDir, '', out);

      // ── Hydrate any dehydrated subdir files the cloud index knows about ──
      const getSandpie = () => window.Sandpie || (window.opener && window.opener.Sandpie) || (window.parent && window.parent !== window && window.parent.Sandpie) || null;
      const spObj = getSandpie();
      const sp = spObj && spObj.syncProvider ? spObj.syncProvider() : null;
      if (sp && sp.cloudIndex && sp.hydrate) {
        const idx = sp.cloudIndex();
        if (idx) {
          const prefix = projectPath.replace(/^\/+/, '') + '/';
          for (const [key, entry] of Object.entries(idx)) {
            if (entry.kind !== 'file' || !key.startsWith(prefix)) continue;
            const rel = key.slice(prefix.length);
            if (out.files.includes(rel)) continue;
            try {
              await sp.hydrate(key);
              out.files.push(rel);
              if (rel.endsWith('.tex')) out.texFiles.push(rel);
            } catch (_) { /* skip files we can't hydrate */ }
          }
        }
      }

      for (const p of out.files) {
        const bytes = await readFileBytes(projectPath + '/' + p);
        fileMap[p] = bytes;
      }

      masterFile = '';
      for (const p of out.texFiles) {
        if (/\bmain\.tex$/i.test(p)) { masterFile = p; break; }
      }
      if (!masterFile) {
        for (const p of out.texFiles) {
          const text = new TextDecoder().decode(fileMap[p].slice(0, 8192));
          if (/^\s*\\\s*documentclass\s*[\[{]/m.test(text)) { masterFile = p; break; }
        }
      }
      if (!masterFile && out.texFiles.length) masterFile = out.texFiles[0];

      renderTree(out);
      $actions.style.display = '';
      $btn.disabled = !masterFile;
      setStatus(masterFile ? 'Found master: /' + projectPath + '/' + masterFile : 'No master file with \\documentclass found.', masterFile ? 'ok' : 'err');
    } catch (e) {
      setStatus('Error loading project: ' + (e && e.message), 'err');
    }
  }

  function renderTree(out) {
    const html = ['<ul>'];
    out.dirs.sort().forEach(d => html.push('<li class="dir">' + d + '/</li>'));
    out.files.sort().forEach(p => {
      html.push('<li class="' + (p === masterFile ? 'master' : '') + '">' + p + '</li>');
    });
    html.push('</ul>');
    $tree.innerHTML = html.join('');
  }

  // ===== BusyTeX Worker =====
  function makeWorkerCode() {
    return `
const BUSYTEX_BASE = '${BUSYTEX_BASE}';

self.Module = {
  locateFile: function(path, prefix) {
    return BUSYTEX_BASE + path;
  }
};

importScripts(BUSYTEX_BASE + 'busytex_pipeline.js');

self.pipeline = null;
self.data_packages_js = [
  BUSYTEX_BASE + 'texlive-basic.js',
  BUSYTEX_BASE + 'ubuntu-texlive-latex-recommended.js',
  BUSYTEX_BASE + 'ubuntu-texlive-latex-extra.js',
  BUSYTEX_BASE + 'ubuntu-texlive-science.js',
  BUSYTEX_BASE + 'ubuntu-texlive-fonts-recommended.js'
];
self.preload_data_packages_js = [
  BUSYTEX_BASE + 'texlive-basic.js',
  BUSYTEX_BASE + 'ubuntu-texlive-latex-recommended.js',
  BUSYTEX_BASE + 'ubuntu-texlive-latex-extra.js',
  BUSYTEX_BASE + 'ubuntu-texlive-science.js',
  BUSYTEX_BASE + 'ubuntu-texlive-fonts-recommended.js'
];

onmessage = async ({data}) => {
  const {action, files, main_tex_path, bibtex, verbose, driver} = data;

  if (action === 'init') {
    try {
      self.pipeline = new BusytexPipeline(
        BUSYTEX_BASE + 'busytex.js',
        BUSYTEX_BASE + 'busytex.wasm',
        self.data_packages_js,
        self.preload_data_packages_js,
        [],
        msg => postMessage({type: 'print', text: msg}),
        applet_versions => postMessage({type: 'initialized', versions: applet_versions}),
        true,
        BusytexPipeline.ScriptLoaderWorker
      );
    } catch (err) {
      postMessage({type: 'error', text: 'Init error: ' + err.message + '\\n' + err.stack});
    }
    return;
  }

  if (action === 'compile') {
    if (!self.pipeline) {
      postMessage({type: 'error', text: 'Pipeline not initialized'});
      return;
    }
    try {
      postMessage({type: 'print', text: 'Resolving packages ( analysing \\\\usepackage ) ...'});
      const result = await self.pipeline.compile(
        files, main_tex_path,
        bibtex === null ? null : !!bibtex,
        verbose || 'silent',
        driver || 'xetex_bibtex8_dvipdfmx',
        self.data_packages_js
      );
      postMessage({
        type: 'done',
        pdf: result.pdf,
        log: result.log,
        exit_code: result.exit_code,
        logs: result.logs
      });
    } catch (err) {
      postMessage({type: 'error', text: 'Compile error: ' + err.message + '\\n' + err.stack});
    }
  }
};
`;
  }

  function getOrCreateWorker() {
    if (worker) return worker;
    const code = makeWorkerCode();
    const blob = new Blob([code], {type: 'application/javascript'});
    const url = URL.createObjectURL(blob);
    worker = new Worker(url);
    return worker;
  }

  function terminateWorker() {
    if (worker) { worker.terminate(); worker = null; }
  }

  // ===== Compilation =====
  $btn.addEventListener('click', async () => {
    $btn.disabled = true;
    $progBar.classList.add('visible');
    setProgress(0);
    $log.textContent = ''; $log.classList.remove('visible');
    setStatus('Initializing BusyTeX compiler (first run ~120 MB download)…');

    let logs = [];

    try {
      const w = getOrCreateWorker();

      // Initialize pipeline
      w.postMessage({action: 'init'});
      await new Promise((resolve, reject) => {
        const onMsg = (e) => {
          const d = e.data;
          if (d.type === 'error') { w.removeEventListener('message', onMsg); reject(new Error(d.text)); return; }
          if (d.type === 'print') { logs.push(d.text); setStatus(d.text); }
          if (d.type === 'initialized') { w.removeEventListener('message', onMsg); resolve(); }
        };
        w.addEventListener('message', onMsg);
      });

      setStatus('Reading project files…');
      setProgress(20);

      // Build files array for BusyTeX
      const files = [];
      const BINARY_RE = /\.(png|jpe?g|gif|bmp|pdf|ttf|otf|woff2?)$/i;
      for (const [relPath, bytes] of Object.entries(fileMap)) {
        const isBinary = BINARY_RE.test(relPath);
        files.push({
          path: relPath,
          contents: isBinary ? bytes : new TextDecoder().decode(bytes)
        });
      }

      let hasBib = false;
      for (const f of files) {
        if (typeof f.contents === 'string' && /\\(bibliography|printbibliography|addbibresource)\b/.test(f.contents)) {
          hasBib = true; break;
        }
      }

      setStatus('Compiling (XeLaTeX)…');
      setProgress(25);
      logAppend('=== BusyTeX compilation started ===');

      w.postMessage({
        action: 'compile',
        files: files,
        main_tex_path: masterFile,
        bibtex: hasBib ? null : false,
        verbose: 'verbose',
        driver: 'xetex_bibtex8_dvipdfmx'
      });

      // Track milestones for live progress
      let compileStage = '';
      let resolveCount = 0;
      let lastPage = 0;

      const result = await new Promise((resolve, reject) => {
        const onMsg = (e) => {
          const d = e.data;
          if (d.type === 'error') { w.removeEventListener('message', onMsg); reject(new Error(d.text)); return; }

          if (d.type === 'print') {
            logs.push(d.text);
            for (const raw of d.text.split(/\r?\n/)) {
              const line = raw.trim();
              if (!line) continue;

              // Data-package preloading messages
              if (/Preparing|download|initialized/i.test(line)) {
                setStatus(line);
                continue;
              }

              // Package resolution
              if (/Resolving packages/i.test(line)) {
                compileStage = 'resolve';
                resolveCount = 0;
                setStatus('Resolving LaTeX packages (first run ~120 MB)...');
                setProgress(25);
                continue;
              }
              if (compileStage === 'resolve' && /^resolving\s+\//i.test(line)) {
                resolveCount++;
                setProgress(25 + Math.min(15, resolveCount * 0.4));
                continue;
              }

              // XeLaTeX engine start
              if (/busytex\s+xelatex/i.test(line)) {
                compileStage = 'xelatex';
                lastPage = 0;
                setStatus('XeLaTeX: starting first pass...');
                setProgress(45);
                continue;
              }
              // BibTeX engine start
              if (/busytex\s+bibtex8/i.test(line)) {
                compileStage = 'bibtex';
                setStatus('BibTeX: processing references...');
                setProgress(72);
                continue;
              }
              // PDF generation (dvipdfmx)
              if (/dvipdfmx|converting\s+xdv|generating\s+pdf/i.test(line)) {
                compileStage = 'pdf';
                setStatus('Generating PDF (dvipdfmx)...');
                setProgress(88);
                continue;
              }

              // XeLaTeX page numbers: [1] [2] [3]
              if (compileStage === 'xelatex') {
                const pm = line.match(/^\[(\d+)\+?\]$/);
                if (pm) {
                  lastPage = parseInt(pm[1], 10);
                  setStatus(`XeLaTeX: processing page ${lastPage}...`);
                  // 2% per page, capped at 85% (unknown total page count)
                  setProgress(Math.min(85, 45 + lastPage * 2));
                  continue;
                }
                // Show current file being loaded (before first page)
                const fm = line.match(/^\(([^)\s]+)/);
                if (fm && lastPage === 0) {
                  const fname = fm[1].split('/').pop();
                  setStatus(`XeLaTeX: loading ${fname}...`);
                }
              }

              // Final output file written
              if (/^Output written\s+on/i.test(line)) {
                setStatus('Finalizing PDF...');
                setProgress(95);
              }
            }
          }

          if (d.type === 'done') { w.removeEventListener('message', onMsg); resolve(d); }
        };
        w.addEventListener('message', onMsg);
      });

      setProgress(100);
      logAppend(result.log);

      if (result.exit_code !== 0 || !result.pdf || result.pdf.length === 0) {
        setStatus('Compilation failed (exit ' + result.exit_code + '). See log below.', 'err');
        $btn.disabled = false;
        return;
      }

      setStatus('Done!', 'ok');
      const blob = new Blob([result.pdf], { type: 'application/pdf' });
      const url  = URL.createObjectURL(blob);
      const outName = (masterFile.split('/').pop() || 'output').replace(/\.tex$/i, '.pdf');

      $stage1.style.display = 'none';
      $stage2.style.display = '';
      $result.innerHTML = '<iframe src="' + url + '" type="application/pdf"></iframe><div style="margin-top:.75rem"><a class="dl" href="' + url + '" download="' + outName + '">Download ' + outName + '</a><button class="secondary" id="backBtn">↺ Back</button></div>';
      document.getElementById('backBtn').addEventListener('click', () => {
        $stage2.style.display = 'none';
        $stage1.style.display = '';
        $btn.disabled = false;
      });

    } catch (e) {
      setStatus('Error: ' + (e && e.message || e), 'err');
      logAppend(logs.join('\n'));
      $btn.disabled = false;
    } finally {
      $progBar.classList.remove('visible');
    }
  });

  $clear.addEventListener('click', () => {
    fileMap = {}; masterFile = '';
    $tree.innerHTML = ''; $actions.style.display = 'none';
    $status.textContent = ''; $status.className = '';
    $log.textContent = ''; $log.classList.remove('visible');
    $result.innerHTML = '';
    $stage1.style.display = ''; $stage2.style.display = 'none';
    terminateWorker();
    $path.textContent = '(cleared)';
  });

  function getProjectPath() {
    const hash = location.hash;
    const m = hash.match(/[#&?]project=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  const initialPath = getProjectPath();
  if (initialPath) loadProject(initialPath);
  else $path.textContent = 'No project selected. Open a .tex file from the file browser.';

  window.addEventListener('hashchange', () => {
    const p = getProjectPath();
    if (p) loadProject(p);
  });
})();