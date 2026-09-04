/** The Atelier entry point. A separate bundle so the game does not carry the editor. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { AtelierApp } from './atelier/AtelierApp'
import './atelier/atelier.css'
import './styles.css'

const host = document.getElementById('root')
if (host === null) throw new Error('Atelier: no #root element to mount into')

createRoot(host).render(
  <StrictMode>
    <AtelierApp />
  </StrictMode>,
)
