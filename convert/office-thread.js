/* SPDX-License-Identifier: MIT */
// Office-thread script for the in-page office renderer (convert/office-engine.html).
// Runs inside the ZetaOffice (LibreOffice WASM) office pthread. Loads a document
// from /tmp and exports it to /tmp as PDF via UNO, using the module-specific PDF
// export filter the main thread selects from the input extension.
import { ZetaHelperThread } from './zeta/zetaHelper.js';

const zHT = new ZetaHelperThread();
const zetajs = zHT.zetajs;
const css = zHT.css;

let xModel;
const bHidden = new css.beans.PropertyValue({ Name: 'Hidden', Value: true });
const bOverwrite = new css.beans.PropertyValue({ Name: 'Overwrite', Value: true });

zHT.thrPort.onmessage = (e) => {
  if (e.data.cmd !== 'convert') throw Error('Unknown message command: ' + e.data.cmd);
  const { from, to, filter, id } = e.data;
  try {
    // Close the previous document first (keep-alive engine converts many files).
    if (xModel !== undefined &&
        xModel.queryInterface(zetajs.type.interface(css.util.XCloseable))) {
      xModel.close(false);
      xModel = undefined;
    }
    xModel = zHT.desktop.loadComponentFromURL('file://' + from, '_blank', 0, [bHidden]);
    if (!xModel) throw Error('document failed to load (unsupported or corrupt file?)');
    const bFilter = new css.beans.PropertyValue({ Name: 'FilterName', Value: filter });
    xModel.storeToURL('file://' + to, [bOverwrite, bFilter]);
    zetajs.mainPort.postMessage({ cmd: 'converted', id, from, to });
  } catch (err) {
    let msg;
    try { const exc = zetajs.catchUnoException(err); msg = zetajs.getAnyType(exc) + ': ' + exc.Message; }
    catch (_) { msg = String(err && err.message || err); }
    zetajs.mainPort.postMessage({ cmd: 'error', id, error: msg });
  }
};

zHT.thrPort.postMessage({ cmd: 'ready' });
