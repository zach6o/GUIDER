for (const [id, type] of [['connect', 'connect-controller'], ['target', 'connect-target'], ['disconnect', 'disconnect']]) {
  document.getElementById(id).addEventListener('click', async () => {
    const status = document.getElementById('status');
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const result = await chrome.runtime.sendMessage({ type, tabId: tab?.id });
      status.textContent = result?.message || 'Extension unavailable. Reload it and try again.';
    } catch (error) { status.textContent = error.message; }
  });
}
