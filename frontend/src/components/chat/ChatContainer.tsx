import { useChatStore } from '@/stores/chatStore'
import WelcomeScreen from './WelcomeScreen'
import MessageList from './MessageList'
import ChatInput from './ChatInput'

export default function ChatContainer() {
  const { messages, sendMessage } = useChatStore()
  const hasMessages = messages.length > 0

  return (
    <div className="h-full flex flex-col">
      {hasMessages ? (
        <>
          <MessageList />
          <ChatInput onSend={sendMessage} />
        </>
      ) : (
        <div className="flex-1 flex flex-col">
          <WelcomeScreen />
          <div className="mt-auto">
            <ChatInput onSend={sendMessage} />
          </div>
        </div>
      )}
    </div>
  )
}
