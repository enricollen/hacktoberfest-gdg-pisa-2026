import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AdminPage } from './admin/AdminPage.tsx'
import { AnalyticsPage } from './admin/AnalyticsPage.tsx'
import { LoginPage } from './admin/LoginPage.tsx'

// /s/<shop>/{login,admin,analytics}: shop owner pages (static demo mock-ups);
// anything else: the customer experience.
const ownerPage = window.location.pathname.match(/^\/s\/[\w-]+\/(login|admin|analytics)\/?$/)?.[1]
const pages = { login: LoginPage, admin: AdminPage, analytics: AnalyticsPage }
const Page = ownerPage ? pages[ownerPage as keyof typeof pages] : App

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
)
