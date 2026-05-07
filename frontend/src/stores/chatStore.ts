import { create } from 'zustand'
import type { Conversation, Message } from '@/types'
import { chatApi } from '@/lib/api'

interface Provider {
  name: string
  model: string
  base_url: string
  default: boolean
}

interface ChatState {
  conversations: Conversation[]
  currentConversationId: string | null
  messages: Message[]
  isStreaming: boolean
  isLoading: boolean
  error: string | null
  providers: Provider[]
  selectedProvider: string | null

  loadConversations: () => Promise<void>
  loadProviders: () => Promise<void>
  setSelectedProvider: (provider: string) => void
  createConversation: () => Promise<string>
  switchConversation: (id: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  appendMessage: (message: Message) => void
  updateLastMessage: (content: string, status?: Message['status']) => void
  setStreaming: (streaming: boolean) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  isStreaming: false,
  isLoading: false,
  error: null,
  providers: [],
  selectedProvider: localStorage.getItem('selectedProvider') || null,

  loadConversations: async () => {
    try {
      const res = await chatApi.getConversations()
      set({ conversations: res.data.conversations || [] })
    } catch (err) {
      console.error('Failed to load conversations:', err)
    }
  },

  loadProviders: async () => {
    try {
      const res = await chatApi.getProviders()
      const providers = res.data.providers || []
      set({ providers })
      // Auto-select default provider if none selected
      const { selectedProvider } = get()
      if (!selectedProvider && providers.length > 0) {
        const defaultProvider = providers.find((p: Provider) => p.default) || providers[0]
        set({ selectedProvider: defaultProvider.name })
        localStorage.setItem('selectedProvider', defaultProvider.name)
      }
    } catch (err) {
      console.error('Failed to load providers:', err)
    }
  },

  setSelectedProvider: (provider: string) => {
    set({ selectedProvider: provider })
    localStorage.setItem('selectedProvider', provider)
  },

  createConversation: async () => {
    const id = `conv_${Date.now()}`
    set({ currentConversationId: id, messages: [] })
    return id
  },

  switchConversation: async (id) => {
    set({ currentConversationId: id, isLoading: true })
    try {
      const res = await chatApi.getConversation(id)
      set({ messages: res.data.messages || [], isLoading: false })
    } catch (err) {
      set({ messages: [], isLoading: false })
    }
  },

  deleteConversation: async (id) => {
    try {
      await chatApi.deleteConversation(id)
      const { conversations, currentConversationId } = get()
      const newConversations = conversations.filter((c) => c.id !== id)
      set({ conversations: newConversations })
      if (currentConversationId === id) {
        set({ currentConversationId: null, messages: [] })
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  },

  sendMessage: async (content) => {
    const { currentConversationId, messages } = get()

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
      status: 'complete',
    }

    set({
      messages: [...messages, userMessage],
      isStreaming: true,
      error: null,
    })

    const assistantMessage: Message = {
      id: `msg_${Date.now() + 1}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      status: 'streaming',
    }

    set({ messages: [...get().messages, assistantMessage] })

    try {
      const { selectedProvider } = get()
      const res = await chatApi.sendMessage(content, currentConversationId || undefined, selectedProvider || undefined)
      const answer = res.data.answer || '抱歉，我暂时无法回答这个问题。'

      set({
        messages: get().messages.map((m, i) =>
          i === get().messages.length - 1
            ? { ...m, content: answer, status: 'complete' as const }
            : m
        ),
        isStreaming: false,
      })

      // Update conversation list
      get().loadConversations()
    } catch (err) {
      set({
        messages: get().messages.map((m, i) =>
          i === get().messages.length - 1
            ? { ...m, content: '请求失败，请稍后重试。', status: 'error' as const }
            : m
        ),
        isStreaming: false,
        error: '发送消息失败',
      })
    }
  },

  appendMessage: (message) => {
    set({ messages: [...get().messages, message] })
  },

  updateLastMessage: (content, status) => {
    const { messages } = get()
    if (messages.length === 0) return
    const lastIndex = messages.length - 1
    set({
      messages: messages.map((m, i) =>
        i === lastIndex ? { ...m, content, status: status || m.status } : m
      ),
    })
  },

  setStreaming: (streaming) => set({ isStreaming: streaming }),
}))
