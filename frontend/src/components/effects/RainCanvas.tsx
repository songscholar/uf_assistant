import { useEffect, useRef, useState, useCallback } from 'react'
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
    { lengthRange: [8, 15], speedRange: [3, 6], opacityRange: [0.08, 0.22], widthRange: [0.5, 1] },
    { lengthRange: [12, 22], speedRange: [6, 11], opacityRange: [0.15, 0.38], widthRange: [0.8, 1.5] },
    { lengthRange: [16, 30], speedRange: [10, 18], opacityRange: [0.28, 0.6], widthRange: [1, 2.5] },
  ]
  const cfg = configs[layer]
  return {
    x: Math.random() * width,
    y: Math.random() * -height * 1.5,
    length: cfg.lengthRange[0] + Math.random() * (cfg.lengthRange[1] - cfg.lengthRange[0]),
    speed: cfg.speedRange[0] + Math.random() * (cfg.speedRange[1] - cfg.speedRange[0]),
    opacity: cfg.opacityRange[0] + Math.random() * (cfg.opacityRange[1] - cfg.opacityRange[0]),
    width: cfg.widthRange[0] + Math.random() * (cfg.widthRange[1] - cfg.widthRange[0]),
    layer,
    drift: (Math.random() - 0.5) * 0.6,
  }
}

function createSplash(x: number, y: number): Splash {
  const particles = []
  const count = 3 + Math.floor(Math.random() * 4)
  for (let i = 0; i < count; i++) {
    particles.push({
      dx: (Math.random() - 0.5) * 5,
      dy: -Math.random() * 3.5 - 0.5,
      size: 0.5 + Math.random() * 1.8,
    })
  }
  return { x, y, life: 0, maxLife: 12 + Math.floor(Math.random() * 10), particles }
}

export default function RainCanvas({ enabled }: RainCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>(0)
  const dropsRef = useRef<RainDrop[]>([])
  const splashesRef = useRef<Splash[]>([])
  const lastTimeRef = useRef(0)
  const fpsRef = useRef(60)

  // 使用 state 直接管理背景图片，React 可以追踪变化
  const [bgImageObj, setBgImageObj] = useState<HTMLImageElement | null>(null)

  const { config } = useRainStore()
  const intensity = config?.intensity ?? 0.5
  const speed = config?.speed ?? 0.2
  const refract = config?.refract ?? 1.0
  const fog = config?.fog ?? 0.3
  const glass = config?.glass ?? 0.0
  const bgMode = config?.bgMode ?? 'default'
  const bgImageUrl = config?.bgImage ?? null

  // 加载背景图片 — 简化为 useEffect + state
  useEffect(() => {
    if (!enabled) {
      setBgImageObj(null)
      return
    }
    if (!bgImageUrl || bgMode === 'default') {
      setBgImageObj(null)
      return
    }

    const img = new Image()
    img.onload = () => setBgImageObj(img)
    img.onerror = () => setBgImageObj(null)
    img.src = bgImageUrl

    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [enabled, bgImageUrl, bgMode])

  // 渲染循环
  useEffect(() => {
    if (!enabled) return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let width = window.innerWidth
    let height = window.innerHeight

    function resize() {
      if (!canvas || !ctx) return
      width = window.innerWidth
      height = window.innerHeight
      const realW = Math.floor(width * dpr)
      const realH = Math.floor(height * dpr)
      if (canvas.width !== realW || canvas.height !== realH) {
        canvas.width = realW
        canvas.height = realH
      }
      canvas.style.width = width + 'px'
      canvas.style.height = height + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resize()

    // 初始化雨滴
    const area = width * height
    const baseCount = Math.floor(area / 5000)
    const count = Math.max(40, Math.floor(baseCount * intensity))

    const layerDistribution = [0.45, 0.35, 0.2]
    dropsRef.current = []
    for (let layer = 0; layer < 3; layer++) {
      const layerCount = Math.max(8, Math.floor(count * layerDistribution[layer]))
      for (let i = 0; i < layerCount; i++) {
        dropsRef.current.push(createDrop(width, height, layer))
      }
    }

    let adaptiveSkip = 0
    let skipCounter = 0
    lastTimeRef.current = 0
    fpsRef.current = 60

    const hasValidImage = bgImageObj && bgImageObj.complete && bgImageObj.naturalWidth > 0

    function render(timestamp: number) {
      if (!ctx || !canvas) return

      // FPS
      if (lastTimeRef.current > 0) {
        const delta = timestamp - lastTimeRef.current
        const instantFps = 1000 / Math.max(delta, 1)
        fpsRef.current = fpsRef.current * 0.9 + instantFps * 0.1
      }
      lastTimeRef.current = timestamp

      if (fpsRef.current < 30) adaptiveSkip = 1
      else if (fpsRef.current > 45) adaptiveSkip = 0

      skipCounter++
      const shouldRenderSplash = adaptiveSkip === 0 || skipCounter % 2 === 0

      // 清空画布
      ctx.clearRect(0, 0, width, height)

      // 绘制背景
      if (hasValidImage) {
        const img = bgImageObj
        const imgAspect = img.naturalWidth / img.naturalHeight
        const canvasAspect = width / height
        let drawW: number, drawH: number, drawX: number, drawY: number
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

        // 暗化叠加层
        ctx.fillStyle = `rgba(8, 12, 24, ${0.35 + glass * 0.3})`
        ctx.fillRect(0, 0, width, height)
      } else {
        // 默认深蓝渐变背景
        const gradient = ctx.createLinearGradient(0, 0, 0, height)
        gradient.addColorStop(0, '#080c18')
        gradient.addColorStop(0.35, '#0a1020')
        gradient.addColorStop(0.65, '#0c1428')
        gradient.addColorStop(1, '#060a14')
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, width, height)
      }

      // 雾气模糊效果
      if (fog > 0) {
        ctx.save()
        const blurAmount = fog * 8
        ctx.filter = `blur(${blurAmount}px)`
        ctx.globalAlpha = fog * 0.25
        ctx.drawImage(canvas, 0, 0, width, height)
        ctx.restore()
      }

      const rainColor = { r: 175, g: 215, b: 255 }
      const speedMultiplier = 0.6 + speed * 2.5
      const refractMultiplier = refract

      // 绘制雨滴
      const drops = dropsRef.current
      for (let i = 0; i < drops.length; i++) {
        const drop = drops[i]
        drop.y += drop.speed * speedMultiplier
        drop.x += drop.drift * speedMultiplier * refractMultiplier * 0.5

        if (drop.y > height) {
          if (shouldRenderSplash && drop.layer === 2 && Math.random() < 0.05) {
            splashesRef.current.push(createSplash(drop.x, height - 2))
          }
          drop.y = -drop.length - Math.random() * 120
          drop.x = Math.random() * width
        }
        if (drop.x > width + 10) drop.x = -10
        if (drop.x < -10) drop.x = width + 10

        const driftX = drop.drift * refractMultiplier * 2.5
        const endX = drop.x + driftX
        const endY = drop.y + drop.length

        // 雨滴主体渐变
        const grad = ctx.createLinearGradient(drop.x, drop.y, endX, endY)
        grad.addColorStop(0, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, 0)`)
        grad.addColorStop(0.35, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity * 0.6})`)
        grad.addColorStop(0.65, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity})`)
        grad.addColorStop(1, `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity * 0.15})`)

        ctx.beginPath()
        ctx.moveTo(drop.x, drop.y)
        ctx.lineTo(endX, endY)
        ctx.strokeStyle = grad
        ctx.lineWidth = drop.width
        ctx.lineCap = 'round'
        ctx.stroke()

        // 雨滴头部高光
        if (drop.layer >= 1) {
          ctx.beginPath()
          ctx.arc(endX, endY, drop.width * 0.9, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(${rainColor.r}, ${rainColor.g}, ${rainColor.b}, ${drop.opacity * 0.7})`
          ctx.fill()
        }
      }

      // 绘制水花
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
          const alpha = (1 - progress) * 0.5
          for (const p of splash.particles) {
            const px = splash.x + p.dx * splash.life * 0.5
            const py = splash.y + p.dy * splash.life * 0.5 + 0.12 * splash.life * splash.life
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
      lastTimeRef.current = 0
    }
  }, [enabled, intensity, speed, refract, fog, glass, bgImageObj])

  if (!enabled) return null

  return (
    <canvas
      ref={canvasRef}
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
