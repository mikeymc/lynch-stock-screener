// ABOUTME: Context for sharing agent chat state between components
// ABOUTME: Enables chat history display in sidebar while state lives in AnalysisChat

import { createContext, useContext, useState, useCallback } from 'react'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  // Agent mode toggle
  const [agentMode, setAgentMode] = useState(() => {
    const saved = localStorage.getItem('agentModeEnabled')
    return saved === 'true'
  })

  // Conversation state
  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)

  // Update agent mode and persist to localStorage
  const updateAgentMode = useCallback((enabled) => {
    setAgentMode(enabled)
    localStorage.setItem('agentModeEnabled', enabled.toString())
  }, [])

  // Update conversations list
  const updateConversations = useCallback((convs) => {
    setConversations(convs)
  }, [])

  // Add a new conversation to the list
  const addConversation = useCallback((conv) => {
    setConversations(prev => [conv, ...prev])
  }, [])

  // Update a conversation's title in the list
  const updateConversationTitle = useCallback((conversationId, title) => {
    setConversations(prev => prev.map(c =>
      c.id === conversationId ? { ...c, title } : c
    ))
  }, [])

  // Remove a conversation from the list
  const removeConversation = useCallback((conversationId) => {
    setConversations(prev => prev.filter(c => c.id !== conversationId))
  }, [])

  const value = {
    agentMode,
    setAgentMode: updateAgentMode,
    conversations,
    setConversations: updateConversations,
    addConversation,
    updateConversationTitle,
    removeConversation,
    activeConversationId,
    setActiveConversationId
  }

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChatContext() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChatContext must be used within a ChatProvider')
  }
  return context
}
