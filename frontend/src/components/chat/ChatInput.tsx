import { useState, useRef, useEffect } from 'react'
import { Send, Paperclip, Globe, Sparkles } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSend: (content: string) => void
}

export default function ChatInput({ onSend }: ChatInputProps) {
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { isStreaming, providers, selectedProvider, loadProviders, setSelectedProvider } = useChatStore()

  useEffect(() => {
    loadProviders()
  }, [])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }, [content])

  const handleSubmit = () => {
    if (!content.trim() || isStreaming) return
    onSend(content.trim())
    setContent('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="px-4 pb-4 pt-2">
      <div
        className={cn(
          'bg-bg-card border border-border rounded-2xl shadow-md',
          'transition-all duration-200',
          'hover:shadow-lg focus-within:shadow-lg'
        )}
      >
        {/* Input */}
        <div className="px-3 pt-3">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="给优富助手发送消息..."
            rows={1}
            className={cn(
              'chat-input w-full resize-none bg-transparent text-text-primary text-[15px]',
              'placeholder:text-text-tertiary outline-none border-none',
              'min-h-[40px] max-h-[200px] py-1'
            )}
          />
        </div>

        {/* Bottom toolbar */}
        <div className="flex items-center gap-1 px-3 pb-3 pt-1">
          <ToolbarButton icon={<Paperclip className="w-4 h-4" />} label="附件" />
          <ToolbarButton icon={<Globe className="w-3.5 h-3.5" />} label="联网搜索" />
          <ToolbarButton icon={<Sparkles className="w-3.5 h-3.5" />} label="深度思考" />
          <div className="flex-1" />
          {providers.length > 0 && (
            <select
              value={selectedProvider || ''}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="bg-bg-secondary border border-border rounded-lg px-2 py-1 text-xs text-text-secondary hover:border-border-focus transition-colors duration-150 outline-none cursor-pointer"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.model})
                </option>
              ))}
            </select>
          )}
          <button
            onClick={handleSubmit}
            disabled={!content.trim() || isStreaming}
            className={cn(
              'w-9 h-9 rounded-full flex items-center justify-center shrink-0',
              'transition-all duration-150',
              content.trim() && !isStreaming
                ? 'bg-accent text-white hover:scale-105 hover:shadow-md active:scale-95'
                : 'bg-bg-hover text-text-tertiary'
            )}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

function ToolbarButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-text-tertiary hover:bg-bg-hover hover:text-text-secondary transition-all duration-150 text-xs active:scale-95">
      {icon}
      <span>{label}</span>
    </button>
  )
}
