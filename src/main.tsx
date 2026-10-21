import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ThemeProvider from './components/ThemeProvider'
import { wakeBackend } from './lib/backendStatus'

// Start the agent API now if it is asleep, so it is up before it's needed.
wakeBackend()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
)
