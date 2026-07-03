/* SPDX-License-Identifier: MIT */
// Office-thread script for the docx→PDF converter popup (convert/index.html).
// Runs inside the ZetaOffice (LibreOffice WASM) office pthread; converts
// /tmp/input.<ext> → /tmp/output as PDF via UNO, mirroring zetajs' upstream
// convertpdf example.
import { ZetaHelperThread } from './zeta/zetaHelper.js';

const zHT = new ZetaHelperThread();
const zetajs = zHT.zetajs;
const css = zHT.css;

let xModel;
const bHidden = new css.beans.PropertyValue({ Name: 'Hidden', Value: true });
const bOverwrite = new css.beans.PropertyValue({ Name: 'Overwrite', Value: true });
const bPdf = new css.beans.PropertyValue({ Name: 'FilterName', Value: 'writer_pdf_Export' });

zHT.thrPort.onmessage = (e) => {
  if (e.data.cmd !== 'convert') throw Error('Unknown message command: ' + e.data.cmd);
  const { from, to, id } = e.data;
  try {
    if (xModel !== undefined &&
        xModel.queryInterface(zetajs.type.interface(css.util.XCloseable))) {
      xModel.close(false);
    }
    xModel = zHT.desktop.loadComponentFromURL('file://' + from, '_blank', 0, [bHidden]);
    if (!xModel) throw Error('document failed to load (unsupported or corrupt file?)');
    xModel.storeToURL('file://' + to, [bOverwrite, bPdf]);
    zetajs.mainPort.postMessage({ cmd: 'converted', id, from, to });
  } catch (err) {
    let msg;
    try { const exc = zetajs.catchUnoException(err); msg = zetajs.getAnyType(exc) + ': ' + exc.Message; }
    catch (_) { msg = String(err && err.message || err); }
    zetajs.mainPort.postMessage({ cmd: 'error', id, error: msg });
  }
};

zHT.thrPort.postMessage({ cmd: 'ready' });
