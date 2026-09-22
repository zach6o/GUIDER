/**
 * Document Picture-in-Picture: a real always-on-top OS window rendered from this
 * document (ADR-016). It is the only way a web page can float beside the app the
 * user is working in, and it is why no Electron or native client is needed.
 *
 * Chromium only. Everywhere else the island stays in the page, which is a
 * supported layout rather than a degraded one, so nothing here may throw.
 */

export interface PictureInPictureApi {
  requestWindow(options: { width: number; height: number }): Promise<Window>;
  window: Window | null;
}

/** The one place this capability is detected. `overlay/surface.ts` asks here
 *  rather than looking again, so the offer and the attempt cannot disagree. */
export function api(): PictureInPictureApi | null {
  const candidate = (window as unknown as { documentPictureInPicture?: PictureInPictureApi })
    .documentPictureInPicture;
  return candidate && typeof candidate.requestWindow === 'function' ? candidate : null;
}

export const pipSupported = () => api() !== null;

/** Copy the page's styles so the floating window looks like the island, not like
 *  unstyled markup. Cross-origin sheets cannot be read; those are skipped. */
function adoptStyles(target: Window) {
  for (const sheet of Array.from(document.styleSheets)) {
    if (sheet.href) {
      const link = target.document.createElement('link');
      link.rel = 'stylesheet'; link.href = sheet.href;
      target.document.head.append(link);
      continue;
    }
    try {
      const text = Array.from(sheet.cssRules).map(rule => rule.cssText).join('');
      const style = target.document.createElement('style');
      style.textContent = text;
      target.document.head.append(style);
    } catch {
      const link = sheet.ownerNode as HTMLLinkElement | null;
      if (link?.href) {
        const copy = target.document.createElement('link');
        copy.rel = 'stylesheet';
        copy.href = link.href;
        target.document.head.append(copy);
      }
    }
  }
}

export interface FloatingWindow {
  window: Window;
  mount: HTMLElement;
}

/** Opens the floating window, or returns null when unavailable or declined.
 *  Must be called directly from a user gesture. */
export async function openFloatingWindow(
  onClose: () => void, width = 380, height = 320,
): Promise<FloatingWindow | null> {
  const available = api();
  if (!available) return null;
  let opened: Window;
  try {
    opened = await available.requestWindow({ width, height });
  } catch {
    return null; // Declined, blocked, or already open. The page layout still works.
  }
  adoptStyles(opened);
  opened.document.body.classList.add('island-window');
  const mount = opened.document.createElement('div');
  mount.className = 'island-mount';
  opened.document.body.append(mount);
  opened.addEventListener('pagehide', onClose, { once: true });
  return { window: opened, mount };
}

export function closeFloatingWindow(floating: FloatingWindow | null) {
  try {
    floating?.window.close();
  } catch {
    // Already gone. Closing twice is not an error worth surfacing.
  }
}
