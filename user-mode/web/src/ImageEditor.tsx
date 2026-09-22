import { useEffect, useRef, useState } from 'react';
import { Crop, EyeOff, RotateCcw, Upload, X } from 'lucide-react';
import { editImage, validBox } from './image';
import type { Box } from './types';

export function ImageEditor({ initial, busy, onUpload, onCancel, cloud }: {
  initial: Blob; busy: boolean; onUpload: (blob: Blob) => void; onCancel: () => void; cloud?: string;
}) {
  const [versions, setVersions] = useState<Blob[]>([initial]);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [box, setBox] = useState<Box>({ x: 0, y: 0, width: 100, height: 50 });
  const [mode, setMode] = useState<'crop' | 'hide'>('hide');
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [url, setUrl] = useState('');
  const origin = useRef<{ x: number; y: number } | null>(null);
  const blob = versions[versions.length - 1];
  useEffect(() => { const value = URL.createObjectURL(blob); setUrl(value); return () => URL.revokeObjectURL(value); }, [blob]);
  useEffect(() => {
    let active = true;
    void createImageBitmap(blob).then(bitmap => {
      if (active) {
        setSize({ width: bitmap.width, height: bitmap.height });
        setBox({ x: 0, y: 0, width: Math.min(200, bitmap.width), height: Math.min(60, bitmap.height) });
      }
      bitmap.close();
    });
    return () => { active = false; };
  }, [blob]);
  async function apply() {
    setEditing(true); setError('');
    try { setVersions([...versions, await editImage(blob, box, mode)]); setReviewed(false); }
    catch (error) { setError((error as Error).message); }
    finally { setEditing(false); }
  }
  function point(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: Math.round(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * size.width),
      y: Math.round(Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) * size.height) };
  }
  return <section className="editor" aria-labelledby="preview-title">
    <div className="section-heading"><div><span className="eyebrow">BEFORE YOU SHARE</span><h2 id="preview-title">A quick privacy check.</h2></div>
      <button className="icon-button" aria-label="Cancel image preview" onClick={onCancel} disabled={busy}><X size={20} /></button></div>
    <p className="muted">{cloud ? `Only the reviewed image below goes to ${cloud} when you press Send. Crop out distractions and hide keys, passwords, or personal details.` : 'Only this image will be shared. Crop out distractions and hide keys, passwords, or personal details.'}</p>
    <div className="editor-tools"><button aria-pressed={mode === 'hide'} onClick={() => setMode('hide')}><EyeOff size={16} /> Hide area</button>
      <button aria-pressed={mode === 'crop'} onClick={() => setMode('crop')}><Crop size={16} /> Crop</button>
      <button disabled={versions.length === 1 || busy} onClick={() => { setVersions(versions.slice(0, -1)); setReviewed(false); }}><RotateCcw size={16} /> Undo</button></div>
    <div className="image-stage"><div className="editable-image" onPointerDown={event => {
      if (busy) return; origin.current = point(event); event.currentTarget.setPointerCapture(event.pointerId);
    }} onPointerMove={event => {
      if (!origin.current) return;
      const end = point(event), start = origin.current;
      setBox({ x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.max(1, Math.abs(end.x - start.x)), height: Math.max(1, Math.abs(end.y - start.y)) });
    }} onPointerUp={() => { origin.current = null; }} onPointerCancel={() => { origin.current = null; }}>
      {url && <img src={url} alt="Exact image prepared for upload. Use the selection controls to crop or hide private details." draggable={false} />}
      {size.width > 0 && <div className="selection" style={{ left: `${box.x / size.width * 100}%`, top: `${box.y / size.height * 100}%`, width: `${box.width / size.width * 100}%`, height: `${box.height / size.height * 100}%` }} />}
    </div></div>
    <fieldset className="coordinates" disabled={busy || editing}><legend>Select an area in pixels, or drag on the image</legend>
      {(['x', 'y', 'width', 'height'] as const).map(name => <label key={name}>{name}<input type="number" value={box[name]} min={name === 'x' || name === 'y' ? 0 : 1}
        max={name === 'x' || name === 'width' ? size.width : size.height} onChange={event => setBox({ ...box, [name]: Number(event.target.value) })} /></label>)}
      <button onClick={() => void apply()} disabled={!validBox(box, size.width, size.height)}>{mode === 'crop' ? 'Apply crop' : 'Hide selected area'}</button>
    </fieldset>
    <p className="privacy-note">{(blob.size / 1024).toFixed(0)} KB · {size.width} × {size.height} · PNG · {cloud ? `Destination: ${cloud} · API usage is billed to your account` : 'No external AI provider'}</p>
    <label className="check-label"><input type="checkbox" checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} /> I reviewed this image and hid sensitive information.</label>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="editor-footer"><button className="text-button" onClick={onCancel} disabled={busy}>Cancel</button>
      <button className="primary" disabled={!reviewed || busy || editing} onClick={() => onUpload(blob)}><Upload size={17} />{busy ? (cloud ? 'Getting guidance…' : 'Uploading image…') : (cloud ? `Send to ${cloud}` : 'Upload this image')}</button></div>
  </section>;
}
