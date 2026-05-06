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
  const { isStreaming } = useChatStore()

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
      <div className="bg-bg-card border border-border rounded-2xl shadow-md hover:shadow-lg transition-shadow">
        {/* Toolbar */}
        <div className="flex items-center gap-1 px-3 pt-2">
          <button className="p-1.5 rounded-lg hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-smooth">
            <Paperclip className="w-4 h-4" />
          </button>
          <button className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-smooth text-xs">
            <Globe className="w-3.5 h-3.5" />
            <span>联网搜索</span>
          </button>
          <button className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-smooth text-xs">
            <Sparkles className="w-3.5 h-3.5" />
            <span>深度思考</span>
          </button>
        </div>

        {/* Input */}
        <div className="flex items-end gap-2 px-3 pb-3 pt-1">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="给优富助手发送消息..."
            rows={1}
            className={cn(
              'flex-1 resize-none bg-transparent text-text-primary text-[15px]',
              'placeholder:text-text-tertiary outline-none',
              'min-h-[40px] max-h-[200px] py-2'
            )}
          />
          <button
            onClick={handleSubmit}
            disabled={!content.trim() || isStreaming}
            className={cn(
              'w-9 h-9 rounded-full flex items-center justify-center shrink-0 mb-0.5',
              'transition-all duration-150',
              content.trim() && !isStreaming
                ? 'bg-accent text-white hover:scale-105 hover:shadow-md'
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
