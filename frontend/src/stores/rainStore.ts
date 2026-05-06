import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface RainConfig {
  intensity: number    // 雨势 0-1
  fog: number         // 雾气 0-1
  refract: number     // 折射率 0-2
  glass: number       // 玻璃透明度 0-1
  speed: number       // 雨滴速度 0-1
  bgMode: 'default' | 'image' | 'video'
}

const DEFAULT_CONFIG: RainConfig = {
  intensity: 0.5,
  fog: 0.3,
  refract: 1.0,
  glass: 0.0,
  speed: 0.2,
  bgMode: 'default',
}

interface RainStore {
  config: RainConfig
  uploadFile: File | null  // 运行时持有的上传文件，不持久化
  isPanelOpen: boolean
  setConfig: (config: Partial<RainConfig>) => void
  setUploadFile: (file: File | null) => void
  resetConfig: () => void
  openPanel: () => void
  closePanel: () => void
  togglePanel: () => void
}

export const useRainStore = create<RainStore>()(
  persist(
    (set) => ({
      config: { ...DEFAULT_CONFIG },
      uploadFile: null,
      isPanelOpen: false,

      setConfig: (partial) =>
        set((state) => ({
          config: { ...state.config, ...partial },
        })),

      setUploadFile: (file) => set({ uploadFile: file }),

      resetConfig: () => set({ config: { ...DEFAULT_CONFIG }, uploadFile: null }),

      openPanel: () => set({ isPanelOpen: true }),
      closePanel: () => set({ isPanelOpen: false }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
    }),
    {
      name: 'rain-config-storage',
      partialize: (state) => ({ config: state.config }),
    }
  )
)
