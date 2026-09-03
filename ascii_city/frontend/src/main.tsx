import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './ui/App'
import './styles.css'

const container = document.getElementById('root')
if (!container) throw new Error('The page is missing its root element.')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
