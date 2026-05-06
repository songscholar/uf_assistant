import { useRef, useEffect, useCallback } from 'react'
import { X, RotateCcw, Upload, Cloud, CloudRain } from 'lucide-react'
import { useThemeStore } from '@/stores/themeStore'
import { useRainStore } from '@/stores/rainStore'
import Slider from '@/components/ui/Slider'
import { cn } from '@/lib/utils'

export default function SettingsPanel() {
  const { theme } = useThemeStore()
  const { config, uploadFile, isPanelOpen, closePanel, setConfig, setUploadFile, resetConfig } = useRainStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isRain = theme === 'rain'

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') closePanel()
    },
    [closePanel]
  )

  useEffect(() => {
    if (isPanelOpen) {
      document.addEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = ''
    }
  }, [isPanelOpen, handleKeyDown])

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadFile(file)
    setConfig({
      bgMode: file.type.startsWith('video/') ? 'video' : 'image',
    })
  }

  if (!isPanelOpen) return null

  return (
    <>
      {/* Overlay */}
      <div
        className={cn(
          'fixed inset-0 z-[200] transition-all duration-400',
          isPanelOpen
            ? 'bg-black/25 backdrop-blur-[8px] opacity-100 pointer-events-auto'
            : 'bg-black/0 backdrop-blur-none opacity-0 pointer-events-none'
        )}
        onClick={closePanel}
      />

      {/* Panel */}
      <div
        className={cn(
          'fixed top-1/2 left-1/2 w-[420px] max-w-[calc(100vw-32px)] max-h-[80vh]',
          'rounded-[20px] z-[201] overflow-y-auto',
          'transition-all duration-[450ms]',
          isPanelOpen
            ? 'opacity-100 visible'
            : 'opacity-0 invisible',
          isRain
            ? 'bg-[rgba(15,23,42,0.2)] border border-[rgba(255,255,255,0.08)] backdrop-blur-[40px] saturate-[1.3]'
            : 'bg-bg-card/75 border border-border backdrop-blur-[40px] saturate-[1.2]'
        )}
        style={{
          transform: isPanelOpen
            ? 'translate(-50%, -50%) scale(1) translateY(0)'
            : 'translate(-50%, -50%) scale(0.88) translateY(20px)',
          transitionTimingFunction: isPanelOpen
            ? 'cubic-bezier(0.34, 1.56, 0.64, 1)'
            : 'cubic-bezier(0.25, 0.1, 0.25, 1)',
          boxShadow: isRain
            ? '0 24px 80px rgba(0,0,0,0.4)'
            : '0 0 0 1px rgba(0,0,0,0.02), 0 8px 40px rgba(0,0,0,0.06), 0 30px 80px -20px rgba(0,0,0,0.1)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-7 pt-6 pb-4 border-b border-border/60">
          <h3 className="text-base font-semibold text-text-primary tracking-tight">设置</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { resetConfig(); setUploadFile(null) }}
              className="p-2 rounded-xl hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-smooth"
              title="重置默认值"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={closePanel}
              className="p-2 rounded-xl bg-bg-hover/50 hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-smooth"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-7 py-5">
          {/* Rain Settings Group */}
          {isRain && (
            <div
              className={cn(
                'transition-all duration-300',
                isPanelOpen ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
              )}
              style={{ transitionDelay: '80ms' }}
            >
              <div className="text-[11px] font-semibold text-accent tracking-[0.08em] uppercase mb-4">
                🌧️ 雨滴玻璃
              </div>

              <Slider
                label="雨势"
                value={config.intensity}
                min={0}
                max={1}
                step={0.01}
                valueFormatter={(v) => v.toFixed(2)}
                onChange={(v) => setConfig({ intensity: v })}
              />

              <Slider
                label="雾气"
                value={config.fog}
                min={0}
                max={1}
                step={0.01}
                valueFormatter={(v) => v.toFixed(2)}
                onChange={(v) => setConfig({ fog: v })}
              />

              <Slider
                label="折射率"
                value={config.refract}
                min={0}
                max={2}
                step={0.01}
                valueFormatter={(v) => v.toFixed(2)}
                onChange={(v) => setConfig({ refract: v })}
              />

              <Slider
                label="玻璃透明度"
                value={config.glass}
                min={0}
                max={1}
                step={0.01}
                valueFormatter={(v) => v.toFixed(2)}
                onChange={(v) => setConfig({ glass: v })}
              />

              <Slider
                label="雨滴速度"
                value={config.speed}
                min={0}
                max={1}
                step={0.01}
                valueFormatter={(v) => v.toFixed(2)}
                onChange={(v) => setConfig({ speed: v })}
              />

              {/* Background Mode */}
              <div className="mt-5">
                <div className="text-[13px] font-medium text-text-secondary mb-3">背景</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setConfig({ bgMode: 'default' }); setUploadFile(null) }}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium transition-smooth',
                      config.bgMode === 'default'
                        ? 'bg-accent text-white'
                        : 'bg-bg-hover text-text-secondary hover:bg-bg-active'
                    )}
                  >
                    <Cloud className="w-3.5 h-3.5" />
                    默认
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium transition-smooth',
                      config.bgMode === 'image' || config.bgMode === 'video'
                        ? 'bg-accent text-white'
                        : 'bg-bg-hover text-text-secondary hover:bg-bg-active'
                    )}
                  >
                    <Upload className="w-3.5 h-3.5" />
                    上传
                  </button>
                </div>

                {uploadFile && !uploadFile.type.startsWith('video/') && (
                  <div className="mt-3 relative rounded-xl overflow-hidden border border-border">
                    <img
                      src={URL.createObjectURL(uploadFile)}
                      alt="Background preview"
                      className="w-full h-24 object-cover"
                    />
                    <button
                      onClick={() => { setConfig({ bgMode: 'default' }); setUploadFile(null) }}
                      className="absolute top-1.5 right-1.5 p-1 rounded-lg bg-black/50 text-white hover:bg-black/70 transition-smooth"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                )}
                {uploadFile && uploadFile.type.startsWith('video/') && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-text-secondary">
                    <span className="truncate">{uploadFile.name}</span>
                    <button
                      onClick={() => { setConfig({ bgMode: 'default' }); setUploadFile(null) }}
                      className="p-1 rounded-lg hover:bg-bg-hover text-text-tertiary"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                )}

                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,video/*"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </div>
            </div>
          )}

          {/* Non-rain message */}
          {!isRain && (
            <div className="text-center py-8 text-text-tertiary">
              <CloudRain className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="text-sm">切换到 🌧️ 雨天模式以配置雨滴效果</p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
