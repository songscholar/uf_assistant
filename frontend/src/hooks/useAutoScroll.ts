import { useRef, useEffect, useCallback } from 'react'

export function useAutoScroll<T extends HTMLElement>(deps: unknown[]) {
  const ref = useRef<T>(null)
  const shouldScroll = useRef(true)

  const scrollToBottom = useCallback(() => {
    if (ref.current && shouldScroll.current) {
      ref.current.scrollTop = ref.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, deps)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const handleScroll = () => {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
      shouldScroll.current = isNearBottom
    }

    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  return { ref, scrollToBottom }
}
