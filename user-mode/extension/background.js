// Only the two explicitly selected tabs are connected. No keys, pixels or history.
let controller = null, target = null;
const send = (port, message) => { try { port?.postMessage(message); } catch { /* disconnected */ } };
function status() {
  send(controller?.port, { type: 'status', connected: true,
    target: target ? { handle: target.handle, label: target.label, revision: target.revision } : null });
}
function clearTarget() {
  const old = target; target = null;
  send(old?.port, { type: 'detach' }); old?.port?.disconnect(); status();
}
function disconnect() {
  const old = controller; controller = null;
  clearTarget(); send(old?.port, { type: 'detached' }); old?.port?.disconnect();
}
const text = (value, max = 1200) => typeof value === 'string' ? value.slice(0, max) : '';
function cleanState(input) {
  const point = input.target;
  return { type: 'state', active: input.active === true, finished: input.finished === true,
    approval: input.approval === true, busy: input.busy === true,
    title: text(input.title, 160), message: text(input.message), where: text(input.where, 500),
    revision: Number.isSafeInteger(input.revision) ? input.revision : -1,
    target: point && Number.isFinite(point.x) && Number.isFinite(point.y)
      && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1
      ? { x: point.x, y: point.y, label: text(point.label, 120) } : null };
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.url !== chrome.runtime.getURL('popup.html')) return;
  (async () => {
    if (message.type === 'disconnect') { disconnect(); return 'Extension disconnected. Sharing stops if it was using this tab guide.'; }
    const tab = await chrome.tabs.get(message.tabId);
    if (!/^https?:\/\//.test(tab.url || '')) throw new Error('Open a normal HTTPS website. Browser settings and extension-store pages cannot show the guide.');
    if (message.type === 'connect-controller') {
      const [check] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => ({
        valid: Boolean(document.querySelector('[data-guider-controller]')), origin: location.origin,
      }) });
      if (!check.result?.valid) throw new Error('Open Automatic guide in Guider, then connect here.');
      disconnect(); controller = { tabId: tab.id, origin: check.result.origin, port: null };
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['controller.js'] });
      return 'Guider connected. Open the website you want help with, then choose “Show guidance on this tab”.';
    }
    if (message.type === 'connect-target') {
      if (!controller?.port) throw new Error('Connect your Guider page first.');
      if (tab.id === controller.tabId) throw new Error('Choose the other website you want guidance on.');
      clearTarget();
      const handle = crypto.randomUUID();
      const [result] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN',
        func: (handle, origin) => {
          if (!navigator.mediaDevices?.setCaptureHandleConfig) return false;
          navigator.mediaDevices.setCaptureHandleConfig({ handle, exposeOrigin: false, permittedOrigins: [origin] });
          return true;
        }, args: [handle, controller.origin] });
      if (!result.result) throw new Error('This page cannot identify its shared tab. Use an HTTPS website in desktop Chrome or Edge.');
      target = { tabId: tab.id, handle, label: (tab.title || 'Selected tab').slice(0, 120), revision: 0, port: null };
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['overlay.js'] });
      status();
      return 'Guide ball enabled. Return to Guider, share this exact browser tab and press Start watching.';
    }
    throw new Error('Unknown extension action.');
  })().then(message => reply({ message }), error => reply({ message: error.message }));
  return true;
});
chrome.runtime.onConnect.addListener(port => {
  const tabId = port.sender?.tab?.id;
  if (port.sender?.frameId !== 0) { port.disconnect(); return; }
  if (port.name === 'guider-controller' && tabId === controller?.tabId) {
    controller.port = port; status();
    port.onDisconnect.addListener(() => { if (controller?.port === port) disconnect(); });
    port.onMessage.addListener(message => {
      if (controller?.port !== port) return;
      if (message.type === 'hello') status();
      if (message.type === 'shutdown') disconnect();
      if (!target?.port || message.handle !== target.handle) return;
      if (message.type === 'state') send(target.port, cleanState(message));
      if (message.type === 'prepare' || message.type === 'restore') send(target.port, {
        type: message.type, id: text(message.id, 100),
      });
    });
  } else if (port.name === 'guider-target' && tabId === target?.tabId) {
    target.port = port;
    port.onDisconnect.addListener(() => { if (target?.port === port) clearTarget(); });
    port.onMessage.addListener(message => {
      if (target?.port !== port) return;
      if (message.type === 'command' && ['stop', 'pause', 'exit', 'approve', 'return'].includes(message.command)) {
        send(controller?.port, { type: 'command', command: message.command, handle: target.handle });
        if (message.command === 'return') void chrome.tabs.update(controller.tabId, { active: true });
      }
      if (message.type === 'invalidate') {
        target.revision++; send(port, { type: 'revision', revision: target.revision }); status();
      }
      if (message.type === 'prepared') send(controller?.port, { type: 'prepared', id: text(message.id, 100), handle: target.handle });
    });
    status();
  } else port.disconnect();
});
