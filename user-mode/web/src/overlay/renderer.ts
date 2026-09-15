/**
 * Drawing a mark on the window Guider is mirroring.
 *
 * The mark arrives in normalised `0..1` frame coordinates, and this multiplies
 * by the element it is drawn into. That indirection is the whole point: the
 * video element resizes, the user zooms, the window moves to another monitor
 * with another DPI, and none of it reaches the mark — only the multiplier
 * changes ([ADR-020](../../../../docs/user-mode-guide/adr/020-overlay-surfaces.md)).
 *
 * The surface here is Guider's own mirror, not the user's desktop. A web page
 * cannot draw on another application's window, and this file does not pretend
 * otherwise; the same payload drives a native overlay when that client exists.
 */

export interface MarkPayload {
  kind: 'circle' | 'underline' | 'spotlight' | 'pointer';
  box: [number, number, number, number];
  label: string;
}

export interface Placement {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Where a video's picture actually sits inside its element.
 *
 *  `object-fit: contain` letterboxes: the element is one shape and the picture
 *  another, so a mark placed against the element would drift by the size of the
 *  bars. This computes the picture's own rectangle instead. */
export function pictureBox(
  element: { clientWidth: number; clientHeight: number },
  videoWidth: number,
  videoHeight: number,
): Placement {
  const { clientWidth, clientHeight } = element;
  if (!videoWidth || !videoHeight || !clientWidth || !clientHeight) {
    return { left: 0, top: 0, width: clientWidth, height: clientHeight };
  }
  const scale = Math.min(clientWidth / videoWidth, clientHeight / videoHeight);
  const width = videoWidth * scale;
  const height = videoHeight * scale;
  return {
    left: (clientWidth - width) / 2,
    top: (clientHeight - height) / 2,
    width,
    height,
  };
}

/** The mark's rectangle in element pixels, or null when it would be invisible.
 *
 *  Anything that lands smaller than a couple of pixels is dropped rather than
 *  drawn: a one-pixel ring is not guidance, it is a speck. */
export function place(mark: MarkPayload, picture: Placement): Placement | null {
  const [left, top, right, bottom] = mark.box;
  const box = {
    left: picture.left + left * picture.width,
    top: picture.top + top * picture.height,
    width: (right - left) * picture.width,
    height: (bottom - top) * picture.height,
  };
  if (box.width < 2 || box.height < 2) return null;
  return box;
}

/** Which side a label can sit on without covering what it names.
 *
 *  A label over its own target is worse than no label, so it goes above when
 *  there is room, below when there is not, and inside only when the box is large
 *  enough that it cannot hide anything small. */
export function labelSide(box: Placement, picture: Placement): 'above' | 'below' | 'inside' {
  if (box.top - picture.top > 26) return 'above';
  if (picture.top + picture.height - (box.top + box.height) > 26) return 'below';
  return 'inside';
}

/** Where the label's own top edge goes, given the side it was assigned.
 *
 *  Below means below the box, so it starts where the box ends; above and inside
 *  both start at the box's top edge and are lifted or nudged by the stylesheet,
 *  which is the only place that knows how tall the text is. */
export function labelTop(box: Placement, side: 'above' | 'below' | 'inside'): number {
  return side === 'below' ? box.top + box.height : box.top;
}

export interface DrawOptions {
  reducedMotion?: boolean;
}

/**
 * Draw one mark into a container, replacing whatever was there.
 *
 * Returns whether anything was drawn, because a mark that cannot be placed is a
 * reportable event rather than a silent nothing — guidance carries on either
 * way, since the instruction says where to look in words.
 */
export function draw(
  container: HTMLElement,
  mark: MarkPayload | null,
  video: { clientWidth: number; clientHeight: number; videoWidth: number; videoHeight: number },
  options: DrawOptions = {},
): boolean {
  container.replaceChildren();
  if (!mark) return false;
  const picture = pictureBox(video, video.videoWidth, video.videoHeight);
  const box = place(mark, picture);
  if (!box) return false;

  const shape = document.createElement('div');
  shape.className = `mark mark-${mark.kind}${options.reducedMotion ? '' : ' mark-animated'}`;
  shape.style.left = `${box.left}px`;
  shape.style.top = `${box.top}px`;
  shape.style.width = `${box.width}px`;
  shape.style.height = `${box.height}px`;
  // The mark is decoration for anyone who can see it; the label below is the
  // part that has to work without sight.
  shape.setAttribute('aria-hidden', 'true');

  const side = labelSide(box, picture);
  const label = document.createElement('span');
  label.className = `mark-label mark-label-${side}`;
  label.textContent = mark.label;
  label.style.left = `${box.left}px`;
  label.style.top = `${labelTop(box, side)}px`;
  label.style.minWidth = `${box.width}px`;

  if (mark.kind === 'spotlight') {
    // Everything except the box is dimmed, so the dimming is the mark and the
    // box itself stays untouched.
    const dim = document.createElement('div');
    dim.className = 'mark-dim';
    dim.setAttribute('aria-hidden', 'true');
    dim.style.clipPath = `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0, `
      + `${box.left}px ${box.top}px, ${box.left}px ${box.top + box.height}px, `
      + `${box.left + box.width}px ${box.top + box.height}px, `
      + `${box.left + box.width}px ${box.top}px, ${box.left}px ${box.top}px)`;
    container.append(dim);
  }
  container.append(shape, label);
  return true;
}
