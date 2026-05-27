import { useState, useRef, useCallback } from 'react'

/**
 * Voice Recorder Hook
 *
 * Records audio via MediaRecorder, uploads to /api/speech/transcribe for STT.
 *
 * @param {function} onTranscribed - callback(text: string)
 */
export function useVoiceRecorder(onTranscribed) {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [error, setError] = useState(null)
  const [duration, setDuration] = useState(0)

  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const streamRef = useRef(null)

  const startRecording = useCallback(async () => {
    setError(null)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
      })
      streamRef.current = stream

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/wav'

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null

        const blob = new Blob(chunksRef.current, { type: mimeType })
        if (blob.size < 1000) { setError('录音太短，请重试'); return }

        setIsTranscribing(true)
        try {
          const ext = mimeType.includes('webm') ? 'webm' : 'wav'
          const formData = new FormData()
          formData.append('file', blob, `voice.${ext}`)

          const resp = await fetch('/api/speech/transcribe', { method: 'POST', body: formData })
          const data = await resp.json()

          if (data.error) {
            setError(data.error)
          } else if (data.text) {
            onTranscribed(data.text)
          } else {
            setError('未识别到语音内容')
          }
        } catch (e) {
          setError('语音识别请求失败: ' + e.message)
        }
        setIsTranscribing(false)
      }

      recorder.start(100)
      setIsRecording(true)
      setDuration(0)
      timerRef.current = setInterval(() => setDuration((d) => d + 1), 1000)

    } catch (e) {
      if (e.name === 'NotAllowedError') setError('麦克风权限被拒绝')
      else if (e.name === 'NotFoundError') setError('未检测到麦克风设备')
      else setError('无法启动录音: ' + e.message)
    }
  }, [onTranscribed])

  const stopRecording = useCallback(() => {
    clearInterval(timerRef.current)
    setIsRecording(false)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
  }, [])

  const cancelRecording = useCallback(() => {
    clearInterval(timerRef.current)
    setIsRecording(false)
    setError(null)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = null
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [])

  return {
    isRecording,
    isTranscribing,
    duration,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  }
}
