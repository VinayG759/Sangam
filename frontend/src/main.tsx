import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import CitizenPortal from './pages/CitizenPortal.tsx'

const path = window.location.pathname;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {path === '/report' ? <CitizenPortal /> : <App />}
  </StrictMode>,
)
