/**
 * Wake-phrase matching.
 *
 * Kept as a pure function so it can be unit-tested without a microphone or a
 * browser speech engine. Matching is intentionally forgiving about casing,
 * punctuation and extra words, but strict about whole words: "synthesis" or
 * "synthesizer" must never trigger the wake word "synthia".
 */

export const DEFAULT_WAKE_PHRASE = "synthia";

/** Lower-case, strip punctuation, collapse whitespace. */
export function normalizeWakeText(text: string): string {
  return text
    .toLowerCase()
    // Anything that is not a letter or digit becomes a space, so "synthia's"
    // and "synthia," both reduce to the bare word.
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function words(text: string): string[] {
  const normalized = normalizeWakeText(text);
  return normalized ? normalized.split(" ") : [];
}

/**
 * True when `text` contains the wake phrase as a contiguous run of whole words.
 * Supports multi-word phrases (e.g. "hey synthia") and tolerates surrounding
 * punctuation and other speech.
 */
export function matchesWakePhrase(
  text: string,
  phrase: string = DEFAULT_WAKE_PHRASE,
): boolean {
  const target = words(phrase);
  if (target.length === 0) return false;

  const spoken = words(text);
  if (spoken.length < target.length) return false;

  for (let start = 0; start <= spoken.length - target.length; start += 1) {
    let matched = true;
    for (let offset = 0; offset < target.length; offset += 1) {
      if (spoken[start + offset] !== target[offset]) {
        matched = false;
        break;
      }
    }
    if (matched) return true;
  }
  return false;
}
