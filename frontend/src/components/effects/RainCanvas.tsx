import { useEffect, useRef } from 'react'

interface RainDrop {
  x: number
  y: number
  length: number
  speed: number
  opacity: number
  width: number
  layer: number // 0: background, 1: mid, 2: foreground
  drift: number // horizontal drift
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
  intensity?: number // 0-1
  speed?: number // 0-2
}

function createDrop(width: number, height: number, layer: number): RainDrop {
  const configs = [
    // background layer
    { lengthRange: [8, 15], speedRange: [3, 6], opacityRange: [0.05, 0.15], widthRange: [0.5, 1] },
    // mid layer
    { lengthRange: [12, 22], speedRange: [6, 11], opacityRange: [0.12, 0.3], widthRange: [0.8, 1.5] },
    // foreground layer
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

export default function RainCanvas({ enabled, intensity = 0.5, speed = 1 }: RainCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>(0)
  const dropsRef = useRef<RainDrop[]>([])
  const splashesRef = useRef<Splash[]>([])
  const frameCountRef = useRef(0)
  const lastTimeRef = useRef(0)
  const fpsRef = useRef(60)

  useEffect(() => {
    if (!enabled) return

    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Limit DPR for performance
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    let width = window.innerWidth
    let height = window.innerHeight

    function resize() {
      if (!canvas) return
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = width + 'px'
      canvas.style.height = height + 'px'
      ctx?.scale(dpr, dpr)
    }

    resize()

    // Initialize drops based on intensity and screen size
    const area = width * height
    const baseCount = Math.floor(area / 8000)
    const count = Math.floor(baseCount * intensity)

    const layerDistribution = [0.45, 0.35, 0.2] // bg, mid, fg percentages
    dropsRef.current = []
    for (let layer = 0; layer < 3; layer++) {
      const layerCount = Math.floor(count * layerDistribution[layer])
      for (let i = 0; i < layerCount; i++) {
        dropsRef.current.push(createDrop(width, height, layer))
      }
    }

    // Frame rate adaptive rendering
    let adaptiveSkip = 0
    let skipCounter = 0

    function render(timestamp: number) {
      if (!ctx || !canvas) return

      // FPS calculation
      if (lastTimeRef.current > 0) {
        const delta = timestamp - lastTimeRef.current
        const instantFps = 1000 / delta
        fpsRef.current = fpsRef.current * 0.9 + instantFps * 0.1
      }
      lastTimeRef.current = timestamp

      // Adaptive: if FPS drops below 30, skip every other frame for splashes
      if (fpsRef.current < 30) {
        adaptiveSkip = 1
      } else if (fpsRef.current > 45) {
        adaptiveSkip = 0
      }

      skipCounter++
      const shouldRenderSplash = adaptiveSkip === 0 || skipCounter % 2 === 0

      ctx.clearRect(0, 0, width, height)

      // Rain color based on theme - cool blue-white for rain
      const rainColor = { r: 147, g: 197, b: 253 } // blue-300

      // Update and draw drops
      const drops = dropsRef.current
      for (let i = 0; i < drops.length; i++) {
        const drop = drops[i]
        drop.y += drop.speed * speed
        drop.x += drop.drift * speed

        // Wrap around
        if (drop.y > height) {
          // Chance to create splash on foreground drops
          if (shouldRenderSplash && drop.layer === 2 && Math.random() < 0.08) {
            splashesRef.current.push(createSplash(drop.x, height - 2))
          }

          drop.y = -drop.length - Math.random() * 50
          drop.x = Math.random() * width
        }
        if (drop.x > width) drop.x = 0
        if (drop.x < 0) drop.x = width

        // Draw drop
        const gradient = ctx.createLinearGradient(drop.x, drop.y, drop.x + drop.drift, drop.y + drop.length)
        gradient.addColorStop(0, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, 0)`)
        gradient.addColorStop(0.5, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity})`)
        gradient.addColorStop(1, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity * 0.3})`)

        ctx.beginPath()
        ctx.moveTo(drop.x, drop.y)
        ctx.lineTo(drop.x + drop.drift, drop.y + drop.length)
        ctx.strokeStyle = gradient
        ctx.lineWidth = drop.width
        ctx.lineCap = 'round'
        ctx.stroke()
      }

      // Update and draw splashes
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
  }, [enabled, intensity, speed])

  if (!enabled) return null

  return (
    <canvas
      ref={canvasRef}
      className="rain-canvas"
      style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0, pointerEvents: 'none' }}
    />
  )
}
