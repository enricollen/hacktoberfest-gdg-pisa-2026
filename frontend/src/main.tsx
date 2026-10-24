import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AdminPage } from './admin/AdminPage.tsx'

// /s/<shop>/admin: shop owner console (static demo mock-up); anything else: customer experience.
const isAdmin = /^\/s\/[\w-]+\/admin\/?$/.test(window.location.pathname)

createRoot(document.getElementById('root')!).render(
  <StrictMode>{isAdmin ? <AdminPage /> : <App />}</StrictMode>,
)
