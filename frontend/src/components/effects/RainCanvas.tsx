import { useEffect } from 'react'
import { useRainStore } from '@/stores/rainStore'

declare global {
  interface Window {
    initRain: () => void
    destroyRain: () => void
    __rainConfig: { rain: number; fog: number; refract: number; glass: number; speed: number }
    __rainMedia: {
      mode: () => string
      setMode: (m: string) => void
      reset: () => void
      setUpload: (file: File) => void
    }
  }
}

interface RainCanvasProps {
  enabled: boolean
}

export default function RainCanvas({ enabled }: RainCanvasProps) {
  const { config, uploadFile } = useRainStore()

  // sync config to window.__rainConfig
  useEffect(() => {
    if (!enabled) return
    window.__rainConfig = {
      rain: config.intensity,
      fog: config.fog,
      refract: config.refract,
      glass: config.glass,
      speed: config.speed,
    }
  }, [enabled, config.intensity, config.fog, config.refract, config.glass, config.speed])

  // upload file → rain media
  useEffect(() => {
    if (uploadFile && window.__rainMedia) {
      window.__rainMedia.setUpload(uploadFile)
    } else if (!uploadFile && enabled && window.__rainMedia) {
      window.__rainMedia.reset()
    }
  }, [uploadFile, enabled])

  return null
}
