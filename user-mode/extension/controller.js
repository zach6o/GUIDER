(() => {
  globalThis.__guiderControllerDispose?.();
  const port = chrome.runtime.connect({ name: 'guider-controller' });
  let disposed = false;
  const post = message => window.postMessage({ source: 'guider-extension', ...message }, location.origin);
  const receive = event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.source !== 'guider-page') return;
    const data = event.data;
    if (['hello', 'state', 'prepare', 'restore', 'shutdown'].includes(data.type)) {
      try { port.postMessage(data); } catch { post({ type: 'status', connected: false, target: null }); }
    }
  };
  window.addEventListener('message', receive);
  const heartbeat = setInterval(() => { try { port.postMessage({ type: 'hello' }); } catch { dispose(); } }, 10000);
  function dispose() {
    if (disposed) return; disposed = true;
    clearInterval(heartbeat); window.removeEventListener('message', receive);
    window.removeEventListener('pagehide', dispose); port.disconnect();
    post({ type: 'status', connected: false, target: null });
  }
  globalThis.__guiderControllerDispose = dispose;
  window.addEventListener('pagehide', dispose, { once: true });
  port.onMessage.addListener(message => {
    if (message.type === 'detached') dispose(); else post(message);
  });
  port.onDisconnect.addListener(dispose);
})();
