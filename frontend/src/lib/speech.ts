/**
 * Voice input and playback.
 *
 * Preferred path: MediaRecorder → Sarvam (Indic) / Groq Whisper →
 * Sarvam Bulbul (Indic) or Edge-TTS. Browser SpeechRecognition /
 * SpeechSynthesis stay as fallbacks.
 *
 * Types for SpeechRecognition are declared structurally — TS's DOM lib
 * does not expose the webkit-prefixed constructors.
 */

import { fetchSpeech, transcribeAudio } from './api'
import { getDetectedLang } from './language'

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

export function isRecordingSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  )
}

export function isMicSupported(): boolean {
  return isRecordingSupported() || isSpeechSupported()
}

export interface ActiveRecording {
  stop: () => Promise<Blob>
  cancel: () => void
}

export interface LiveCapture {
  stop: () => Promise<{ text: string; language?: string }>
}

/**
 * Record while the user talks and transcribe the growing clip so the
 * text field updates during speech, not only after Stop.
 */
export async function startLiveCapture(
  onPartial: (text: string) => void,
  locale = 'en-IN',
): Promise<LiveCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) =>
    MediaRecorder.isTypeSupported(type),
  )
  const chunks: BlobPart[] = []
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  const mimeType = recorder.mimeType || mime || 'audio/webm'
  let lastText = ''
  let lastLanguage: string | undefined
  let busy = false
  let queued = false
  let stopDictation: (() => void) | null = null

  const blobFromChunks = () => new Blob(chunks, { type: mimeType })

  const flush = async () => {
    if (busy) {
      queued = true
      return
    }
    const blob = blobFromChunks()
    if (blob.size < 2500) return
    busy = true
    try {
      const result = await transcribeAudio(blob)
      if (result.text.trim()) {
        lastText = result.text.trim()
        lastLanguage = result.language
        onPartial(lastText)
      }
    } catch {
      // Keep recording; a later chunk or the final stop can still succeed.
    } finally {
      busy = false
      if (queued) {
        queued = false
        void flush()
      }
    }
  }

  recorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data)
    void flush()
  }
  recorder.start(900)
  const tick = window.setInterval(() => {
    if (recorder.state === 'recording') {
      try {
        recorder.requestData()
      } catch {
        // Some browsers throw if a slice is already pending.
      }
    }
  }, 900)

  if (isSpeechSupported()) {
    stopDictation = startDictation(
      {
        onResult: (interim, final) => {
          const spoken = `${final}${interim}`.replace(/\s+/g, ' ').trim()
          if (spoken) onPartial(spoken)
        },
        onEnd: () => {},
        onError: () => {},
      },
      locale,
    )
  }

  const stopTracks = () => {
    stream.getTracks().forEach((track) => track.stop())
  }

  return {
    stop: () =>
      new Promise((resolve, reject) => {
        stopDictation?.()
        stopDictation = null
        window.clearInterval(tick)
        recorder.onstop = () => {
          stopTracks()
          const finish = async () => {
            while (busy) {
              await new Promise((wait) => setTimeout(wait, 80))
            }
            const blob = blobFromChunks()
            if (blob.size < 800) {
              resolve({ text: lastText, language: lastLanguage })
              return
            }
            try {
              const result = await transcribeAudio(blob)
              resolve({
                text: result.text.trim() || lastText,
                language: result.language || lastLanguage,
              })
            } catch (error) {
              if (lastText) resolve({ text: lastText, language: lastLanguage })
              else reject(error)
            }
          }
          void finish()
        }
        recorder.onerror = () => {
          stopTracks()
          if (lastText) resolve({ text: lastText, language: lastLanguage })
          else reject(new Error('recording-failed'))
        }
        try {
          if (recorder.state === 'recording') recorder.stop()
          else {
            stopTracks()
            resolve({ text: lastText, language: lastLanguage })
          }
        } catch {
          stopTracks()
          resolve({ text: lastText, language: lastLanguage })
        }
      }),
  }
}

export async function startRecording(): Promise<ActiveRecording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) =>
    MediaRecorder.isTypeSupported(type),
  )
  const chunks: BlobPart[] = []
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)

  recorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data)
  }
  recorder.start()

  const stopTracks = () => {
    stream.getTracks().forEach((track) => track.stop())
  }

  return {
    stop: () =>
      new Promise((resolve, reject) => {
        recorder.onstop = () => {
          stopTracks()
          resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
        }
        recorder.onerror = () => {
          stopTracks()
          reject(new Error('recording-failed'))
        }
        recorder.stop()
      }),
    cancel: () => {
      try {
        recorder.stop()
      } catch {
        // Already stopped.
      }
      stopTracks()
    },
  }
}

/**
 * Start dictating. Returns a `stop` function that cancels recognition
 * without firing onError. Supports language parameter (defaults to 'te-IN' with fallback to 'ur-PK' and 'en-US').
 */
export function startDictation(callbacks: DictationCallbacks, preferredLang: string = 'te-IN'): () => void {
  const Ctor = getRecognitionCtor()
  if (!Ctor) {
    callbacks.onError('unsupported')
    return () => { }
  }

  const recognition = new Ctor()
  recognition.interimResults = true
  recognition.maxAlternatives = 1
  recognition.continuous = true
  recognition.lang = preferredLang

  let finalText = ''
  let stopped = false
  let fallbackStep = 0
  const fallbackLangs = [preferredLang, 'ur-PK', 'en-US'].filter((v, i, a) => a.indexOf(v) === i)

  recognition.onresult = (event) => {
    let rebuiltFinal = ''
    let interim = ''
    for (let i = 0; i < event.results.length; i++) {
      const result = event.results[i]
      const piece = result[0]?.transcript ?? ''
      if (result.isFinal) rebuiltFinal += `${piece} `
      else interim += piece
    }
    finalText = rebuiltFinal
    callbacks.onResult(interim, finalText)
  }

  recognition.onend = () => {
    if (stopped) {
      callbacks.onEnd()
      return
    }
    try {
      recognition.start()
    } catch {
      callbacks.onEnd()
    }
  }

  recognition.onerror = (event) => {
    if (event.error === 'aborted' || event.error === 'no-speech') {
      return
    }
    // Language transcription unavailable — try next fallback language.
    if (
      fallbackStep < fallbackLangs.length - 1 &&
      (event.error === 'language-not-supported' ||
        event.error === 'network' ||
        event.error === 'service-not-allowed')
    ) {
      fallbackStep++
      recognition.lang = fallbackLangs[fallbackStep]
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
    stopped = true
    try {
      recognition.abort()
    } catch {
      // Recognition already gone — nothing to stop.
    }
  }
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Read text aloud using browser SpeechSynthesis. Auto-detects Telugu, Urdu, or English.
 */
function prepareSpeechText(text: string): string {
  return text
    .replace(/\bHDPE\b/gi, 'H D P E')
    .replace(/\bPET\b/gi, 'P E T')
    .replace(/\bPVC\b/gi, 'P V C')
}

export function speakText(text: string, onEnd?: () => void): () => void {
  if (!isSpeechSynthesisSupported()) {
    onEnd?.()
    return () => { }
  }

  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(prepareSpeechText(text))
  const voices = window.speechSynthesis.getVoices()

  const containsTelugu = /[\u0C00-\u0C7F]/.test(text)
  const containsUrdu = /[\u0600-\u06FF]/.test(text)

  if (containsTelugu) {
    const teluguVoice = voices.find((v) => v.lang.startsWith('te'))
    if (teluguVoice) utterance.voice = teluguVoice
    utterance.lang = 'te-IN'
  } else if (containsUrdu) {
    const urduVoice = voices.find((v) => v.lang.startsWith('ur'))
    if (urduVoice) utterance.voice = urduVoice
    utterance.lang = 'ur-PK'
  } else {
    utterance.lang = 'en-US'
  }

  if (onEnd) {
    utterance.onend = () => onEnd()
    utterance.onerror = () => onEnd()
  }

  window.speechSynthesis.speak(utterance)

  return () => {
    window.speechSynthesis.cancel()
  }
}

let currentAudio: HTMLAudioElement | null = null
let speechToken = 0
let currentAbort: AbortController | null = null

function stopCurrentAudio(): void {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio = null
  }
  if (isSpeechSynthesisSupported()) {
    window.speechSynthesis.cancel()
  }
}

export function cancelSpeech(): void {
  speechToken += 1
  currentAbort?.abort()
  currentAbort = null
  stopCurrentAudio()
}

/**
 * Speak with Sarvam Bulbul (or Edge-TTS). Falls back to the browser
 * synthesizer if the server is unavailable.
 */
export async function speakReply(text: string, onEnd?: () => void): Promise<() => void> {
  const token = ++speechToken
  currentAbort?.abort()
  const abort = new AbortController()
  currentAbort = abort
  stopCurrentAudio()
  try {
    const blob = await fetchSpeech(text, getDetectedLang(), abort.signal)
    if (token !== speechToken) {
      onEnd?.()
      return () => {}
    }
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    const finish = () => {
      if (currentAudio === audio) currentAudio = null
      URL.revokeObjectURL(url)
      if (token === speechToken) onEnd?.()
    }
    audio.onended = finish
    audio.onerror = finish
    await audio.play()
    if (token !== speechToken) {
      audio.pause()
      URL.revokeObjectURL(url)
      onEnd?.()
      return () => {}
    }
    return () => {
      cancelSpeech()
      URL.revokeObjectURL(url)
    }
  } catch (error) {
    const aborted =
      (error instanceof DOMException && error.name === 'AbortError') || token !== speechToken
    if (aborted) {
      onEnd?.()
      return () => {}
    }
    return speakText(text, onEnd)
  }
}
