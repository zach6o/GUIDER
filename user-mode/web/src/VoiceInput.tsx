import { useEffect, useRef, useState } from 'react';
import { Dictation, recognitionFactory } from './guide/dictation';

export function VoiceInput({ onUse, disabled }: { onUse: (text: string) => void; disabled: boolean }) {
  const [open, setOpen] = useState(false), [accepted, setAccepted] = useState(false);
  const [listening, setListening] = useState(false), [text, setText] = useState('');
  const [error, setError] = useState('');
  const recorder = useRef<Dictation | null>(null);
  const supported = Boolean(recognitionFactory());
  useEffect(() => {
    function cancel() { recorder.current?.cancel(); setListening(false); }
    function hidden() { if (document.hidden) cancel(); }
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('offline', cancel);
    return () => {
      recorder.current?.cancel(); document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('offline', cancel);
    };
  }, []);
  useEffect(() => { if (disabled) { recorder.current?.cancel(); setListening(false); } }, [disabled]);
  if (!supported) return <p className="privacy-note">Voice input is unavailable in this browser. Type your task above.</p>;
  if (!open) return <button className="text-button" disabled={disabled} onClick={() => setOpen(true)}>Dictate your task</button>;
  return <section className="voice-input" aria-label="Voice input">
    <p>Your browser’s speech service may send audio to its provider. Guider does not save audio.
      Dictation lasts up to 30 seconds. Review and edit the text before using it.</p>
    <label className="check-label"><input type="checkbox" checked={accepted} disabled={listening || disabled}
      onChange={event => setAccepted(event.target.checked)} /> Allow my browser’s speech service for this dictation.</label>
    <div className="plan-buttons">
      {!listening ? <button className="text-button" disabled={!accepted || disabled} onClick={() => {
        const factory = recognitionFactory(); if (!factory) return;
        setText(''); setError(''); setListening(true);
        recorder.current = new Dictation(factory, { text: setText, ended: () => setListening(false), error: setError });
        recorder.current.start();
      }}>Start dictation</button> : <button className="primary" onClick={() => recorder.current?.stop()}>Stop listening</button>}
      <button className="text-button" onClick={() => {
        recorder.current?.cancel(); setListening(false); setText(''); setAccepted(false); setOpen(false);
      }}>Cancel dictation</button>
    </div>
    {listening && <p role="status">Microphone on — listening for your task.</p>}
    {error && <p role="alert">{error}</p>}
    <label>Review transcript<textarea value={text} maxLength={4000} disabled={listening}
      onChange={event => setText(event.target.value)} /></label>
    <button className="text-button" disabled={listening || disabled || !text.trim()} onClick={() => {
      onUse(text.trim()); setText(''); setOpen(false); setAccepted(false);
    }}>Use this text</button>
  </section>;
}
