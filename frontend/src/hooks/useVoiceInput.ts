import { useCallback, useEffect, useRef, useState } from 'react'

type SpeechResultEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

type RecInstance = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: SpeechResultEvent) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
}

type SpeechWindow = Window & {
  SpeechRecognition?: new () => RecInstance
  webkitSpeechRecognition?: new () => RecInstance
}

function getSR(): (new () => RecInstance) | undefined {
  const w = window as SpeechWindow
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export function useVoiceInput(onTranscript: (text: string) => void) {
  const [isListening, setIsListening] = useState(false)
  const [isSupported, setIsSupported] = useState(false)
  const recognitionRef = useRef<RecInstance | null>(null)
  const cbRef = useRef(onTranscript)
  cbRef.current = onTranscript

  useEffect(() => {
    setIsSupported(!!getSR())
  }, [])

  const start = useCallback(() => {
    const SR = getSR()
    if (!SR) return
    const rec = new SR()
    rec.lang = 'en-US'
    rec.continuous = false
    rec.interimResults = false
    rec.onresult = (e) => {
      const text = Array.from(e.results)
        .map((r) => r[0].transcript)
        .join('')
      if (text) cbRef.current(text)
    }
    rec.onerror = () => setIsListening(false)
    rec.onend = () => setIsListening(false)
    recognitionRef.current = rec
    rec.start()
    setIsListening(true)
  }, [])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setIsListening(false)
  }, [])

  const toggle = useCallback(() => {
    if (isListening) stop()
    else start()
  }, [isListening, start, stop])

  return { isListening, isSupported, toggle }
}
