import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_WAKE_PHRASE,
  matchesWakePhrase,
  normalizeWakeText,
} from "../wake/phrase";
import { useWakeWord } from "../wake/useWakeWord";

/**
 * A minimal fake of the Web Speech API surface used for keyword spotting, so we
 * can drive the wake hook without a real microphone or vendor service.
 */
class FakeRecognition {
  static instances: FakeRecognition[] = [];

  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onresult: ((event: SpeechRecognitionEvent) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onstart: (() => void) | null = null;

  started = false;
  aborted = false;

  constructor() {
    FakeRecognition.instances.push(this);
  }

  start() {
    this.started = true;
  }

  stop() {
    this.started = false;
  }

  abort() {
    this.aborted = true;
    this.started = false;
  }

  /** Simulate the engine recognising `transcript`. */
  emitResult(transcript: string) {
    const results = [[{ transcript }]] as unknown as SpeechRecognitionResultList;
    this.onresult?.({ resultIndex: 0, results } as SpeechRecognitionEvent);
  }
}

function installFake(ctor: unknown) {
  (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition = ctor;
}

function removeFakes() {
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition;
  delete (window as unknown as { webkitSpeechRecognition?: unknown })
    .webkitSpeechRecognition;
}

afterEach(() => {
  FakeRecognition.instances = [];
  removeFakes();
  vi.restoreAllMocks();
});

describe("wake-phrase matching", () => {
  it("normalises case and punctuation", () => {
    expect(normalizeWakeText("  Hey,  SYNTHIA!  ")).toBe("hey synthia");
  });

  it("matches the phrase tolerantly", () => {
    expect(matchesWakePhrase("synthia")).toBe(true);
    expect(matchesWakePhrase("Hey Synthia, what's up?")).toBe(true);
    expect(matchesWakePhrase("SYNTHIA")).toBe(true);
  });

  it("is strict about whole words", () => {
    expect(matchesWakePhrase("synthesis is cool")).toBe(false);
    expect(matchesWakePhrase("the synthesizer")).toBe(false);
    expect(matchesWakePhrase("synthetic")).toBe(false);
  });

  it("supports multi-word phrases and rejects empties", () => {
    expect(matchesWakePhrase("ok hey synthia now", "hey synthia")).toBe(true);
    expect(matchesWakePhrase("hey there", "hey synthia")).toBe(false);
    expect(matchesWakePhrase("", DEFAULT_WAKE_PHRASE)).toBe(false);
  });
});

describe("useWakeWord", () => {
  it("stays off until the user opts in", () => {
    installFake(FakeRecognition);
    const onWake = vi.fn();
    const { result } = renderHook(() =>
      useWakeWord({ enabled: false, paused: false, language: "en-US", onWake }),
    );

    expect(result.current.status).toBe("off");
    expect(FakeRecognition.instances).toHaveLength(0);
  });

  it("reports unsupported browsers instead of failing silently", () => {
    removeFakes();
    const { result } = renderHook(() =>
      useWakeWord({ enabled: true, paused: false, language: "en-US", onWake: vi.fn() }),
    );

    expect(result.current.status).toBe("unsupported");
    expect(result.current.unsupportedReason).toBeTruthy();
  });

  it("arms the detector and reacts to the wake phrase", async () => {
    installFake(FakeRecognition);
    const onWake = vi.fn();
    const { result } = renderHook(() =>
      useWakeWord({ enabled: true, paused: false, language: "en-US", onWake }),
    );

    await waitFor(() => expect(result.current.status).toBe("waiting"));
    expect(FakeRecognition.instances).toHaveLength(1);

    act(() => {
      FakeRecognition.instances[0].emitResult("hey synthia, list my instances");
    });

    expect(onWake).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("detected");
  });

  it("releases the mic on detection and does not re-arm from onend", async () => {
    installFake(FakeRecognition);
    const { result } = renderHook(() =>
      useWakeWord({ enabled: true, paused: false, language: "en-US", onWake: vi.fn() }),
    );
    await waitFor(() => expect(result.current.status).toBe("waiting"));

    act(() => {
      FakeRecognition.instances[0].emitResult("synthia");
    });

    // The engine reports its own stop; that must not spin up a second session.
    act(() => {
      FakeRecognition.instances[0].onend?.();
    });

    expect(FakeRecognition.instances).toHaveLength(1);
    expect(FakeRecognition.instances[0].started).toBe(false);
  });

  it("re-arms if the recorder never takes over after detection", () => {
    vi.useFakeTimers();
    installFake(FakeRecognition);
    const { result } = renderHook(() =>
      useWakeWord({ enabled: true, paused: false, language: "en-US", onWake: vi.fn() }),
    );
    expect(result.current.status).toBe("waiting");

    act(() => {
      FakeRecognition.instances[0].emitResult("synthia");
    });
    expect(result.current.status).toBe("detected");

    // No pause arrives, so the detector must arm itself again.
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(FakeRecognition.instances).toHaveLength(2);
    expect(result.current.status).toBe("waiting");

    vi.useRealTimers();
  });

  it("surfaces a permission denial as an error state", async () => {
    installFake(FakeRecognition);
    const { result } = renderHook(() =>
      useWakeWord({ enabled: true, paused: false, language: "en-US", onWake: vi.fn() }),
    );
    await waitFor(() => expect(result.current.status).toBe("waiting"));

    act(() => {
      FakeRecognition.instances[0].onerror?.({ error: "not-allowed" });
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error).toMatch(/permission/i);
  });

  it("releases the microphone while the recorder is active", async () => {
    installFake(FakeRecognition);
    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useWakeWord({ enabled: true, paused, language: "en-US", onWake: vi.fn() }),
      { initialProps: { paused: false } },
    );
    await waitFor(() => expect(result.current.status).toBe("waiting"));
    expect(FakeRecognition.instances[0].aborted).toBe(false);

    rerender({ paused: true });

    // The detector session is torn down (aborted) so it cannot hold the mic.
    await waitFor(() => expect(FakeRecognition.instances[0].aborted).toBe(true));
  });
});
