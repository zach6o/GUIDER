(() => {
  globalThis.__guiderOverlayDispose?.();
  const port = chrome.runtime.connect({ name: 'guider-target' });
  const host = document.createElement('div');
  host.setAttribute('data-guider-overlay', '');
  host.style.cssText = 'all:initial!important;position:fixed!important;inset:0!important;pointer-events:none!important;z-index:2147483647!important';
  const root = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = `
    :host{color-scheme:light}*{box-sizing:border-box}button{font:inherit;cursor:pointer}
    .assistant{position:fixed;right:20px;bottom:20px;width:290px;max-width:calc(100vw - 24px);display:flex;flex-direction:column;align-items:flex-end;gap:10px;font:14px/1.5 system-ui;color:#173e32;pointer-events:none}
    .bubble,.menu{pointer-events:auto;background:#f9fefa;border:1px solid #b2cebf;border-radius:18px;padding:16px;width:100%;box-shadow:0 6px 28px #001f2433;max-height:calc(100vh - 110px);overflow:auto;overflow-wrap:anywhere}
    .heading{display:flex;align-items:center;justify-content:space-between;font-size:10px;letter-spacing:2px;color:#426d5b}.heading button{border:0;background:transparent;font-size:20px;color:#426d5b;letter-spacing:0}
    strong{display:block;margin:8px 0;font-size:14px}p{margin:6px 0;font-size:13px}small{display:block;margin-top:10px;font-size:11px;color:#4c6d60}
    .ball{pointer-events:auto;border:3px solid #fff;border-radius:50%;width:56px;height:56px;min-height:56px;background:#185c45;color:white;font-size:25px;box-shadow:0 4px 20px #001f2444;touch-action:none}
    .menu button,.approve{display:block;width:100%;margin-top:6px;padding:10px;border:0;border-radius:9px;text-align:left;background:#e7f3ec;color:#173e32;font-size:13px}
    button:focus-visible{outline:3px solid #4b9e78;outline-offset:3px}button:disabled{opacity:.5}
    .hint{position:fixed;width:26px;height:26px;margin:-13px;pointer-events:none;border:3px solid #21a56b;border-radius:50%;box-shadow:0 0 0 3px #fff,0 0 0 5px #185c45;font:12px/1.4 system-ui;color:white}
    .hint span{position:absolute;left:30px;top:30px;min-width:100px;max-width:180px;background:#153e31;padding:9px;border:1px solid #75e5a6;border-radius:4px 12px 12px;overflow-wrap:anywhere}
    .hint:before{content:'↖';position:absolute;left:16px;top:11px;font-size:29px;color:#185c45;text-shadow:1px 1px white,-1px -1px white}
    .hint.left span{left:auto;right:30px}.hint.left:before{left:auto;right:16px;transform:scaleX(-1)}
    .hint.above span{top:auto;bottom:30px}.hint.above:before{top:auto;bottom:11px;transform:scaleY(-1)}
    .hint.left.above:before{transform:scale(-1)}[hidden]{display:none!important}
  `;
  root.append(style);
  const make = (tag, className, text) => {
    const node = document.createElement(tag); if (className) node.className = className;
    if (text) node.textContent = text; return node;
  };
  const assistant = make('aside', 'assistant'); assistant.setAttribute('aria-label', 'Guider tab assistant');
  const bubble = make('section', 'bubble'); bubble.setAttribute('aria-label', 'Guide message');
  const heading = make('div', 'heading', 'GUIDER');
  const dismiss = make('button', '', '×'); dismiss.setAttribute('aria-label', 'Dismiss guide message'); heading.append(dismiss);
  const title = make('strong'), message = make('p'), where = make('small');
  const status = make('div'); status.setAttribute('role', 'status'); status.append(title, message, where);
  const approve = make('button', 'approve', 'I approve this step');
  bubble.append(heading, status, approve);
  const menu = make('section', 'menu'); menu.setAttribute('aria-label', 'Guide options'); menu.hidden = true;
  const ball = make('button', 'ball', '✦'); ball.setAttribute('aria-label', 'Open guide options'); ball.setAttribute('aria-expanded', 'false');
  const hint = make('div', 'hint'); hint.hidden = true; hint.setAttribute('role', 'note');
  const hintLabel = make('span'); hint.append(hintLabel);
  assistant.append(bubble, menu, ball); root.append(hint, assistant); document.documentElement.append(host);
  let revision = 0, dismissed = '', lastKey = '', menuOpen = false, disposed = false, restoreTimer;
  const send = message => { try { port.postMessage(message); } catch { dispose(); } };
  const trusted = callback => event => { if (event.isTrusted) callback(event); };
  const command = name => { send({ type: 'command', command: name }); };
  function showMenu(open) {
    menuOpen = open; menu.hidden = !open; bubble.hidden = open || dismissed === lastKey;
    ball.setAttribute('aria-expanded', String(open)); ball.setAttribute('aria-label', open ? 'Close guide options' : 'Open guide options');
  }
  ball.addEventListener('click', trusted(() => showMenu(!menuOpen)));
  dismiss.addEventListener('click', trusted(() => { dismissed = lastKey; bubble.hidden = true; ball.focus(); }));
  approve.addEventListener('click', trusted(() => { approve.disabled = true; command('approve'); }));
  for (const [label, name] of [['Show current step', 'show'], ['Pause guidance', 'pause'], ['Return to Guider', 'return'], ['Stop screen sharing', 'stop'], ['Exit guide', 'exit']]) {
    const button = make('button', '', label);
    button.addEventListener('click', trusted(() => {
      if (name === 'show') dismissed = ''; else command(name);
      showMenu(false);
    })); menu.append(button);
  }
  root.addEventListener('keydown', event => { if (event.key === 'Escape') { showMenu(false); ball.focus(); } });
  // Move the ball without moving or clicking the underlying website.
  let drag = null, moved = false;
  ball.addEventListener('pointerdown', trusted(event => {
    const bounds = assistant.getBoundingClientRect();
    drag = { x: event.clientX, y: event.clientY, right: innerWidth - bounds.right, bottom: innerHeight - bounds.bottom };
    moved = false; ball.setPointerCapture(event.pointerId);
  }));
  ball.addEventListener('pointermove', event => {
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 6) moved = true;
    if (moved) {
      assistant.style.right = `${Math.max(8, Math.min(innerWidth - 70, drag.right - dx))}px`;
      assistant.style.bottom = `${Math.max(8, Math.min(innerHeight - 70, drag.bottom - dy))}px`;
    }
  });
  ball.addEventListener('pointerup', () => { drag = null; });
  ball.addEventListener('pointercancel', () => { drag = null; });
  ball.addEventListener('click', event => { if (moved) { event.stopImmediatePropagation(); moved = false; } }, true);
  function render(next) {
    title.textContent = next.title; message.textContent = next.message; where.textContent = next.where;
    approve.hidden = !next.approval; approve.disabled = next.busy;
    lastKey = JSON.stringify([next.title, next.message, next.where]);
    bubble.hidden = menuOpen || dismissed === lastKey;
    const point = next.active && !next.approval && next.revision === revision ? next.target : null;
    hint.hidden = !point;
    if (point) {
      hint.style.left = `${point.x * 100}vw`; hint.style.top = `${point.y * 100}vh`;
      hint.className = `hint ${point.x > .65 ? 'left' : ''} ${point.y > .65 ? 'above' : ''}`;
      hintLabel.textContent = `Click here: ${point.label}`; hint.setAttribute('aria-label', `Screen hint: ${point.label}`);
    }
  }
  render({ title: 'Ready to guide this tab', message: 'Return to Guider, share this browser tab, then press Start watching.', where: '', approval: false, busy: false });
  let invalidating = false;
  function invalidate(event) {
    if (event?.composedPath?.().includes(host)) return;
    hint.hidden = true;
    if (!invalidating) {
      invalidating = true; send({ type: 'invalidate' });
      queueMicrotask(() => { invalidating = false; });
    }
  }
  const observer = new MutationObserver(records => {
    if (!host.isConnected) { dispose(); return; }
    if (records.some(record => record.target !== host && !host.contains(record.target))) invalidate();
  });
  observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  for (const event of ['scroll', 'resize', 'pointerdown', 'input']) window.addEventListener(event, invalidate, true);
  const heartbeat = setInterval(() => send({ type: 'heartbeat' }), 10000);
  const restore = () => { clearTimeout(restoreTimer); host.style.setProperty('visibility', 'visible', 'important'); };
  port.onMessage.addListener(data => {
    if (data.type === 'state') render(data);
    if (data.type === 'revision') { revision = data.revision; hint.hidden = true; }
    if (data.type === 'detach') dispose();
    if (data.type === 'prepare') {
      host.style.setProperty('visibility', 'hidden', 'important');
      clearTimeout(restoreTimer); restoreTimer = setTimeout(restore, 2200);
      send({ type: 'prepared', id: data.id });
    }
    if (data.type === 'restore') restore();
  });
  function dispose() {
    if (disposed) return; disposed = true;
    clearInterval(heartbeat); clearTimeout(restoreTimer); observer.disconnect();
    for (const event of ['scroll', 'resize', 'pointerdown', 'input']) window.removeEventListener(event, invalidate, true);
    window.removeEventListener('pagehide', dispose); host.remove(); port.disconnect();
  }
  globalThis.__guiderOverlayDispose = dispose;
  port.onDisconnect.addListener(dispose); window.addEventListener('pagehide', dispose, { once: true });
})();
