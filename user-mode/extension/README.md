# Guider tab companion

Shows the guide ball, step messages and an arrow **inside the browser tab you
choose**. Keep the Guider page open in another tab. Desktop Chrome / Edge only.

## Install once on each computer

1. Download **Guider tab extension** from the Automatic guide page and extract
   the ZIP into a permanent folder. When using this repository, use this folder:
   `D:\PROJECTS\GUIDER\user-mode\extension`.
2. Open `chrome://extensions` (Chrome) or `edge://extensions` (Edge).
3. Turn on **Developer mode**, click **Load unpacked**, and select the folder
   containing `manifest.json`. Pin Guider using the browser's extensions menu.

The extension is a personal, unpacked companion. It is not published in either
browser's extension store. Reload it from the extensions page after updating its
files; then reconnect the two tabs.

## Use it

1. Open Automatic guide in Guider, connect your API key, and confirm your plan.
2. While on Guider, click the extension icon and **Connect this Guider page**.
3. Open the HTTPS website you want help with. Click the extension icon there and
   **Show guidance on this tab**. A round ball appears.
4. Return to Guider. Choose window and permissions, then choose this exact
   **Chrome Tab / Microsoft Edge Tab**, not an application window. Review the
   preview and privacy masks, then press **Start watching**.
5. Switch to the shared tab. Messages and click hints appear there. You perform
   each action yourself. Drag the ball to move it; tap it for current step,
   Pause, Return to Guider, Stop sharing, or Exit. Approve steps in the bubble
   when asked. Stop ends capture; Exit also disconnects Guider and removes the ball.

Arrows clear when the page changes, scrolls, or resizes, and return after a new
screen check. The guide briefly hides itself while a fresh frame is captured so
the AI sees your page rather than its own hints. Rate limits still apply.

A full page navigation/reload removes the injected guide and stops automatic
sharing. Enable the extension on the new page and share again. Single-page
updates and scrolling do not require re-enabling it. Browser settings, protected
extension-store pages, PDFs in the browser viewer, other browser profiles and
native applications cannot receive this overlay. Use the floating-window mode
for native applications; its arrows remain on Guider's preview.

## What it accesses

The distributed manifest requests only `activeTab` and `scripting`. Clicking the
extension grants access to that tab. It has no all-sites permission, backend
credentials, account storage, external network calls, or automatic clicking.
Only current-step text, marker coordinates, capture identity and control commands
pass through the extension. Guider remains responsible for screen capture,
masking, consent, your API connection and provider requests.

Capture Handle binds the overlay to the actual shared browser tab. Selecting a
different tab or choosing a whole application window will not start the in-tab
guide. Closing Guider, disconnecting the extension, losing the chosen document,
Stop, and the existing 15-minute expiry end sharing. Reconnect the extension if
the browser restarts it. Each browser profile/computer needs its own installation.

## Verification

`npm run test:personal` in `user-mode/web` includes a persistent Chromium profile
with this extension installed, real browser-tab capture and synthetic provider
replies. Set `GUIDE_EXTENSION_BROWSER` to an installed Playwright Chromium binary
when its default browser is unavailable. The test adds a localhost-only host
grant to an isolated copy because Playwright cannot click the browser toolbar;
the distributed manifest keeps only `activeTab` and `scripting`.
