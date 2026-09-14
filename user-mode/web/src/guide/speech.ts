/**
 * Reading the current step aloud.
 *
 * Voice is delivery, never authority. It says what the instruction already says
 * and can do nothing else: it cannot claim a step, accept a skip, agree to be
 * watched, or confirm anything. Doc 13 and the voice rules in doc 15 both make
 * that point about voice *input*; this is output, and the same line holds from
 * the other side — hearing an instruction is not performing it.
 *
 * Off by default. A guide that started talking because a page loaded would be a
 * guide that talked over a meeting.
 */

export interface Speaker {
  speak(text: string): void;
  cancel(): void;
  readonly speaking: boolean;
}

/** What the browser exposes, narrowed to what is used. Kept as an interface so
 *  tests drive a fake rather than a global. */
export interface SpeechApi {
  speak(utterance: unknown): void;
  cancel(): void;
  speaking: boolean;
}

export function speechAvailable(): boolean {
  return typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && 'SpeechSynthesisUtterance' in window;
}

/** One sentence per line of the instruction, in the order the island shows them.
 *
 *  Deliberately not the whole card: the confirmation hint is what the user
 *  listens for, and reading the explanation aloud every time turns guidance into
 *  narration. */
export function spokenText(instruction: {
  what: string;
  where?: string | null;
  confirmation_hint?: string | null;
}): string {
  const parts = [instruction.what];
  if (instruction.where) parts.push(instruction.where);
  if (instruction.confirmation_hint) parts.push(`You will know it worked when ${lower(instruction.confirmation_hint)}`);
  return parts.join(' ');
}

function lower(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/**
 * Speaks instructions, one at a time, and stops the moment anything changes.
 *
 * Cancelling before every utterance is the whole behaviour worth naming: a queue
 * of stale instructions read one after another would be actively misleading,
 * because the user would be hearing a step they are already past.
 */
export class InstructionSpeaker implements Speaker {
  private lastSpoken = '';

  constructor(
    private readonly api: SpeechApi,
    private readonly makeUtterance: (text: string) => unknown,
  ) {}

  get speaking(): boolean {
    return this.api.speaking;
  }

  speak(text: string): void {
    if (!text.trim()) return;
    // Never queue. What is on screen now is the only thing worth hearing.
    this.api.cancel();
    this.lastSpoken = text;
    this.api.speak(this.makeUtterance(text));
  }

  /** Speak only if this is different from the last thing said, so a re-render or
   *  a reconnect does not repeat the step at the user. */
  speakOnce(text: string): boolean {
    if (text === this.lastSpoken) return false;
    this.speak(text);
    return true;
  }

  cancel(): void {
    this.api.cancel();
    this.lastSpoken = '';
  }
}

/** The real one, or null where the browser has no speech synthesis. Callers
 *  treat null as "voice is unavailable", never as an error. */
export function browserSpeaker(): InstructionSpeaker | null {
  if (!speechAvailable()) return null;
  const synthesis = window.speechSynthesis as unknown as SpeechApi;
  return new InstructionSpeaker(synthesis, text => {
    const utterance = new window.SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    return utterance;
  });
}
