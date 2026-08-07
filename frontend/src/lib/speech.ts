/**
 * Thin wrapper around the browser Web Speech API (SpeechRecognition).
 *
 * The backend has no audio pipeline, so voice input is handled entirely
 * client-side: the mic dictates into the composer's text box. Urdu is
 * preferred (ur-PK); where a browser can't transcribe it we fall back to
 * en-US, which still captures Roman-Urdu and English. Browsers without any
 * SpeechRecognition support simply don't get a mic button (isSpeechSupported).
 *
 * Types are declared structurally rather than imported, because TS's DOM lib
 * does not expose the webkit-prefixed constructors.
 */

export interface DictationCallbacks {
  /** Fired on each interim update. `interim` is the live fragment, `final` is all finalized text so far. */
  onResult: (interim: string, final: string) => void
  /** Fired when recognition stops, cleanly or not. */
  onEnd: () => void
  /** Fired on a real failure (permission denied, no service, ...). */
  onError: (error: string) => void
}

interface SpeechRecognitionResultLike {
  isFinal: boolean
  length: number
  [index: number]: { transcript: string }
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<SpeechRecognitionResultLike>
}

interface RecognitionLike {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  continuous: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onend: (() => void) | null
  onerror: ((event: { error: string }) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type RecognitionCtor = new () => RecognitionLike

function getRecognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function isSpeechSupported(): boolean {
  return getRecognitionCtor() !== null
}

/**
 * Start dictating. Returns a `stop` function that cancels recognition
 * without firing onError.
 */
export function startDictation(callbacks: DictationCallbacks): () => void {
  const Ctor = getRecognitionCtor()
  if (!Ctor) {
    callbacks.onError('unsupported')
    return () => {}
  }

  const recognition = new Ctor()
  recognition.interimResults = true
  recognition.maxAlternatives = 1
  recognition.continuous = false
  recognition.lang = 'ur-PK'

  let finalText = ''
  let fellBackToEnglish = false

  recognition.onresult = (event) => {
    let interim = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      if (result.isFinal) finalText += `${result[0].transcript} `
      else interim += result[0].transcript
    }
    callbacks.onResult(interim, finalText)
  }

  recognition.onend = () => {
    callbacks.onEnd()
  }

  recognition.onerror = (event) => {
    // We initiated the abort (stop button) — not a failure.
    if (event.error === 'aborted' || event.error === 'no-speech') {
      callbacks.onEnd()
      return
    }
    // Urdu transcription unavailable here — retry once in English.
    if (
      !fellBackToEnglish &&
      (event.error === 'language-not-supported' ||
        event.error === 'network' ||
        event.error === 'service-not-allowed')
    ) {
      fellBackToEnglish = true
      recognition.lang = 'en-US'
      try {
        recognition.start()
      } catch {
        callbacks.onError(event.error)
      }
      return
    }
    callbacks.onError(event.error)
  }

  try {
    recognition.start()
  } catch {
    callbacks.onError('not-allowed')
  }

  return () => {
    try {
      recognition.abort()
    } catch {
      // Recognition already gone — nothing to stop.
    }
  }
}
