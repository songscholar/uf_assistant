import { useAutoScroll } from '@/hooks/useAutoScroll'
import { useChatStore } from '@/stores/chatStore'
import MessageBubble from './MessageBubble'

export default function MessageList() {
  const { messages, sendMessage } = useChatStore()
  const { ref } = useAutoScroll<HTMLDivElement>([messages.length, messages[messages.length - 1]?.content])

  const handleRetry = () => {
    const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user')
    if (lastUserMessage) {
      sendMessage(lastUserMessage.content)
    }
  }

  return (
    <div
      ref={ref}
      className="flex-1 overflow-y-auto"
    >
      {messages.map((message, index) => (
        <MessageBubble
          key={message.id}
          message={message}
          onRetry={index === messages.length - 1 && message.role === 'assistant' ? handleRetry : undefined}
        />
      ))}
    </div>
  )
}
