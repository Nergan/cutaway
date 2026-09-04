/** The game entry point. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import './styles.css'
import { App } from './ui/App'

const host = document.getElementById('root')
if (host === null) throw new Error('Age: no #root element to mount into')

createRoot(host).render(
  // Strict mode double-invokes effects in development, which is how the renderer's teardown
  // path gets exercised on every save rather than only on a real unmount. That has already
  // caught one leaked WebGL context, so it stays on.
  <StrictMode>
    <App />
  </StrictMode>,
)
