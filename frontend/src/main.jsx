import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext'
import { ChatProvider } from './context/ChatContext'
import { ThemeProvider } from './components/theme-provider'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ChatProvider>
          <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme" disableFetch={true}>
            <App />
          </ThemeProvider>
        </ChatProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
