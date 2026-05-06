import { useEffect, useRef } from 'react'
import { useRainStore } from '@/stores/rainStore'

interface RainDrop {
  x: number
  y: number
  length: number
  speed: number
  opacity: number
  width: number
  layer: number
  drift: number
}

interface Splash {
  x: number
  y: number
  life: number
  maxLife: number
  particles: { dx: number; dy: number; size: number }[]
}

interface RainCanvasProps {
  enabled: boolean
}

function createDrop(width: number, height: number, layer: number): RainDrop {
  const configs = [
    { lengthRange: [8, 15], speedRange: [3, 6], opacityRange: [0.05, 0.15], widthRange: [0.5, 1] },
    { lengthRange: [12, 22], speedRange: [6, 11], opacityRange: [0.12, 0.3], widthRange: [0.8, 1.5] },
    { lengthRange: [16, 30], speedRange: [10, 18], opacityRange: [0.2, 0.5], widthRange: [1, 2.5] },
  ]
  const cfg = configs[layer]
  return {
    x: Math.random() * width,
    y: Math.random() * -height,
    length: cfg.lengthRange[0] + Math.random() * (cfg.lengthRange[1] - cfg.lengthRange[0]),
    speed: cfg.speedRange[0] + Math.random() * (cfg.speedRange[1] - cfg.speedRange[0]),
    opacity: cfg.opacityRange[0] + Math.random() * (cfg.opacityRange[1] - cfg.opacityRange[0]),
    width: cfg.widthRange[0] + Math.random() * (cfg.widthRange[1] - cfg.widthRange[0]),
    layer,
    drift: (Math.random() - 0.5) * 0.5,
  }
}

function createSplash(x: number, y: number): Splash {
  const particles = []
  const count = 3 + Math.floor(Math.random() * 4)
  for (let i = 0; i < count; i++) {
    particles.push({
      dx: (Math.random() - 0.5) * 4,
      dy: -Math.random() * 3 - 1,
      size: 0.5 + Math.random() * 1.5,
    })
  }
  return {
    x,
    y,
    life: 0,
    maxLife: 15 + Math.floor(Math.random() * 10),
    particles,
  }
}

export default function RainCanvas({ enabled }: RainCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const bgCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const bgImageRef = useRef<HTMLImageElement | null>(null)
  const rafRef = useRef<number>(0)
  const dropsRef = useRef<RainDrop[]>([])
  const splashesRef = useRef<Splash[]>([])
  const frameCountRef = useRef(0)
  const lastTimeRef = useRef(0)
  const fpsRef = useRef(60)
  const { config } = useRainStore()

  // Load background image when config changes
  useEffect(() => {
    if (config.bgImage && config.bgMode !== 'default') {
      const img = new Image()
      img.onload = () => {
        bgImageRef.current = img
      }
      img.src = config.bgImage
    } else {
      bgImageRef.current = null
    }
  }, [config.bgImage, config.bgMode])

  useEffect(() => {
    if (!enabled) return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    let width = window.innerWidth
    let height = window.innerHeight

    // Background canvas for fog effect
    let bgCanvas = bgCanvasRef.current
    if (!bgCanvas) {
      bgCanvas = document.createElement('canvas')
      bgCanvasRef.current = bgCanvas
    }
    const bgCtx = bgCanvas.getContext('2d')

    function resize() {
      if (!canvas || !bgCanvas || !bgCtx) return
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = width + 'px'
      canvas.style.height = height + 'px'
      ctx?.scale(dpr, dpr)

      bgCanvas.width = width
      bgCanvas.height = height
    }

    resize()

    // Initialize drops based on config intensity
    const area = width * height
    const baseCount = Math.floor(area / 8000)
    const count = Math.floor(baseCount * config.intensity * 2) // scale up for visibility

    const layerDistribution = [0.45, 0.35, 0.2]
    dropsRef.current = []
    for (let layer = 0; layer < 3; layer++) {
      const layerCount = Math.floor(count * layerDistribution[layer])
      for (let i = 0; i < layerCount; i++) {
        dropsRef.current.push(createDrop(width, height, layer))
      }
    }

    let adaptiveSkip = 0
    let skipCounter = 0

    function render(timestamp: number) {
      if (!ctx || !canvas || !bgCanvas || !bgCtx) return

      // FPS calculation
      if (lastTimeRef.current > 0) {
        const delta = timestamp - lastTimeRef.current
        const instantFps = 1000 / delta
        fpsRef.current = fpsRef.current * 0.9 + instantFps * 0.1
      }
      lastTimeRef.current = timestamp

      if (fpsRef.current < 30) {
        adaptiveSkip = 1
      } else if (fpsRef.current > 45) {
        adaptiveSkip = 0
      }
      skipCounter++
      const shouldRenderSplash = adaptiveSkip === 0 || skipCounter % 2 === 0

      // Clear main canvas
      ctx.clearRect(0, 0, width, height)

      // Draw background (custom image or gradient)
      if (bgImageRef.current && (config.bgMode === 'image' || config.bgMode === 'upload')) {
        const img = bgImageRef.current
        const imgAspect = img.width / img.height
        const canvasAspect = width / height
        let drawW, drawH, drawX, drawY
        if (imgAspect > canvasAspect) {
          drawH = height
          drawW = height * imgAspect
          drawX = (width - drawW) / 2
          drawY = 0
        } else {
          drawW = width
          drawH = width / imgAspect
          drawX = 0
          drawY = (height - drawH) / 2
        }
        ctx.drawImage(img, drawX, drawY, drawW, drawH)
      } else {
        // Default: dark blue gradient
        const gradient = ctx.createLinearGradient(0, 0, 0, height)
        gradient.addColorStop(0, '#0f172a')
        gradient.addColorStop(0.5, '#1e293b')
        gradient.addColorStop(1, '#0f172a')
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, width, height)
      }

      // Apply fog / glass blur effect
      if (config.fog > 0 || config.glass > 0) {
        ctx.save()
        const blurAmount = Math.max(config.fog * 8, config.glass * 6)
        ctx.filter = `blur(${blurAmount}px)`
        ctx.globalAlpha = config.fog * 0.5 + config.glass * 0.3
        ctx.drawImage(canvas, 0, 0, width, height)
        ctx.restore()
      }

      const rainColor = { r: 147, g: 197, b: 253 }
      const speedMultiplier = 0.5 + config.speed * 2
      const refractMultiplier = config.refract

      // Draw drops
      const drops = dropsRef.current
      for (let i = 0; i < drops.length; i++) {
        const drop = drops[i]
        drop.y += drop.speed * speedMultiplier
        drop.x += drop.drift * speedMultiplier * refractMultiplier

        if (drop.y > height) {
          if (shouldRenderSplash && drop.layer === 2 && Math.random() < 0.08) {
            splashesRef.current.push(createSplash(drop.x, height - 2))
          }
          drop.y = -drop.length - Math.random() * 50
          drop.x = Math.random() * width
        }
        if (drop.x > width) drop.x = 0
        if (drop.x < 0) drop.x = width

        // Apply refract to horizontal drift
        const driftX = drop.drift * refractMultiplier

        const gradient = ctx.createLinearGradient(
          drop.x,
          drop.y,
          drop.x + driftX,
          drop.y + drop.length
        )
        gradient.addColorStop(0, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, 0)`)
        gradient.addColorStop(0.5, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity})`)
        gradient.addColorStop(1, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity * 0.3})`)

        ctx.beginPath()
        ctx.moveTo(drop.x, drop.y)
        ctx.lineTo(drop.x + driftX, drop.y + drop.length)
        ctx.strokeStyle = gradient
        ctx.lineWidth = drop.width
        ctx.lineCap = 'round'
        ctx.stroke()
      }

      // Draw splashes
      if (shouldRenderSplash) {
        const splashes = splashesRef.current
        for (let i = splashes.length - 1; i >= 0; i--) {
          const splash = splashes[i]
          splash.life++

          if (splash.life >= splash.maxLife) {
            splashes.splice(i, 1)
            continue
          }

          const progress = splash.life / splash.maxLife
          const alpha = (1 - progress) * 0.4

          for (const p of splash.particles) {
            const px = splash.x + p.dx * splash.life * 0.5
            const py = splash.y + p.dy * splash.life * 0.5 + 0.1 * splash.life * splash.life
            const size = p.size * (1 - progress)

            ctx.beginPath()
            ctx.arc(px, py, size, 0, Math.PI * 2)
            ctx.fillStyle = `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${alpha})`
            ctx.fill()
          }
        }
      }

      rafRef.current = requestAnimationFrame(render)
    }

    rafRef.current = requestAnimationFrame(render)
    window.addEventListener('resize', resize)

    return () => {
      cancelAnimationFrame(rafRef.current)
      window.removeEventListener('resize', resize)
      dropsRef.current = []
      splashesRef.current = []
    }
  }, [enabled, config.intensity, config.speed, config.refract, config.fog, config.glass, config.bgMode, config.bgImage])

  if (!enabled) return null

  return (
    <canvas
      ref={canvasRef}
      className="rain-canvas"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  )
}
