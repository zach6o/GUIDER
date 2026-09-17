/** Browser speech is opt-in, bounded, and supplies text only. */
export interface Recognition {
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((event: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
export type RecognitionConstructor = new () => Recognition;
export function recognitionFactory(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null;
  const browser = window as unknown as {
    SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor;
  };
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition ?? null;
}

export class Dictation {
  private recognition: Recognition | null = null;
  private deadline: ReturnType<typeof setTimeout> | null = null;
  private finishing: ReturnType<typeof setTimeout> | null = null;
  constructor(private create: RecognitionConstructor, private hooks: {
    text: (text: string) => void; ended: () => void; error: (message: string) => void;
  }) {}
  start() {
    this.cancel();
    const recognition = new this.create(); this.recognition = recognition;
    recognition.continuous = true; recognition.interimResults = false; recognition.lang = 'en-US';
    recognition.onresult = event => {
      if (this.recognition !== recognition) return;
      this.hooks.text(Array.from(event.results).filter(result => result.isFinal)
        .map(result => result[0].transcript).join(' ').slice(0, 4000));
    };
    recognition.onerror = () => {
      if (this.recognition !== recognition) return;
      this.cancel(); this.hooks.error('Dictation stopped. Check microphone permission or type your task.');
      this.hooks.ended();
    };
    recognition.onend = () => {
      if (this.recognition !== recognition) return;
      this.clearTimers(); this.recognition = null; this.hooks.ended();
    };
    try { recognition.start(); this.deadline = setTimeout(() => this.stop(), 30_000); }
    catch { this.cancel(); this.hooks.error('Dictation could not start. You can type instead.'); this.hooks.ended(); }
  }
  stop() {
    const recognition = this.recognition;
    if (!recognition) return;
    this.clearTimers(); recognition.stop();
    // Stop acquisition immediately; abandon delayed service results after five seconds.
    this.finishing = setTimeout(() => { this.cancel(); this.hooks.ended(); }, 5000);
  }
  cancel() {
    const recognition = this.recognition; this.recognition = null; this.clearTimers();
    if (recognition) {
      recognition.onresult = recognition.onerror = recognition.onend = null;
      recognition.abort();
    }
  }
  private clearTimers() {
    if (this.deadline) clearTimeout(this.deadline);
    if (this.finishing) clearTimeout(this.finishing);
    this.deadline = this.finishing = null;
  }
}
