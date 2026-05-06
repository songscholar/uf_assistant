import { useChatStore } from '@/stores/chatStore'
import { APP_TAGLINE, QUICK_ACTIONS } from '@/lib/constants'
import { TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function WelcomeScreen() {
  const { sendMessage } = useChatStore()

  const handleQuickAction = (prompt: string) => {
    sendMessage(prompt)
  }

  return (
    <div className="h-full flex flex-col items-center justify-center px-4">
      <div className="text-center mb-10">
        <div className="w-16 h-16 rounded-2xl bg-accent flex items-center justify-center mx-auto mb-5 shadow-lg">
          <TrendingUp className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-text-primary mb-2">你好，我是优富</h1>
        <p className="text-text-secondary">{APP_TAGLINE}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full max-w-[640px]">
        {QUICK_ACTIONS.map((action, index) => (
          <button
            key={index}
            onClick={() => handleQuickAction(action.prompt)}
            className={cn(
              'flex items-center gap-3 p-4 rounded-xl border border-border',
              'bg-bg-card hover:border-accent hover:shadow-md',
              'transition-smooth text-left'
            )}
          >
            <span className="text-xl">{action.icon}</span>
            <div>
              <div className="text-sm font-medium text-text-primary">{action.label}</div>
              <div className="text-xs text-text-tertiary mt-0.5 truncate max-w-[180px]">
                {action.prompt.slice(0, 20)}...
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
