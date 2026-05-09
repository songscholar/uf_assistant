import { useState } from 'react'
import { Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Bot, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '@/types'
import { cn, formatTime } from '@/lib/utils'

interface MessageBubbleProps {
  message: Message
  onRetry?: () => void
}

export default function MessageBubble({ message, onRetry }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)
  const [liked, setLiked] = useState<'up' | 'down' | null>(null)
  const [showActions, setShowActions] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={cn(
        'flex gap-3 px-4 py-4 group',
        isUser ? 'flex-row-reverse animate-slide-in-right' : 'flex-row animate-slide-in-left'
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Avatar */}
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5',
          'transition-all duration-300 hover:scale-110 hover:rotate-6',
          isUser ? 'bg-accent' : 'bg-bg-secondary border border-border'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-accent" />
        )}
      </div>

      {/* Content */}
      <div className={cn('flex flex-col max-w-[min(680px,85%)]', isUser && 'items-end')}>
        {/* Bubble */}
        <div
          className={cn(
            'px-4 py-2.5 text-[15px] leading-relaxed',
            'transition-all duration-200',
            isUser
              ? 'bg-accent text-white rounded-2xl rounded-tr-sm hover:shadow-md hover:shadow-accent/20'
              : 'bg-bg-card border border-border rounded-2xl rounded-tl-sm shadow-sm hover:shadow-md'
          )}
        >
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="markdown-body text-text-primary">
              {message.status === 'streaming' && !message.content ? (
                <div className="flex items-center gap-1.5 py-2">
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot" style={{ animationDelay: '200ms' }} />
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot" style={{ animationDelay: '400ms' }} />
                </div>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        {!isUser && message.status === 'complete' && (
          <div
            className={cn(
              'flex items-center gap-0.5 mt-1.5 transition-all duration-200',
              showActions ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-1'
            )}
          >
            <ActionButton
              onClick={handleCopy}
              title="复制"
              active={copied}
            >
              {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
            </ActionButton>
            <ActionButton
              onClick={() => setLiked(liked === 'up' ? null : 'up')}
              title="点赞"
              active={liked === 'up'}
            >
              <ThumbsUp className={cn('w-3.5 h-3.5', liked === 'up' && 'fill-accent text-accent')} />
            </ActionButton>
            <ActionButton
              onClick={() => setLiked(liked === 'down' ? null : 'down')}
              title="点踩"
              active={liked === 'down'}
            >
              <ThumbsDown className={cn('w-3.5 h-3.5', liked === 'down' && 'fill-danger text-danger')} />
            </ActionButton>
            {onRetry && (
              <ActionButton onClick={onRetry} title="重新生成">
                <RotateCcw className="w-3.5 h-3.5" />
              </ActionButton>
            )}
          </div>
        )}

        {/* Timestamp */}
        <span className="text-[11px] text-text-tertiary mt-1 px-1">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  )
}

function ActionButton({
  children,
  onClick,
  title,
  active,
}: {
  children: React.ReactNode
  onClick: () => void
  title: string
  active?: boolean
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'p-1.5 rounded-md text-text-tertiary transition-all duration-150',
        'hover:bg-bg-hover hover:text-text-secondary',
        'active:scale-95',
        active && 'bg-accent-bg text-accent'
      )}
    >
      {children}
    </button>
  )
}
