const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const DOMAIN_RE = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:[/:?#].*)?$/i

export function contactHref(contact) {
  const value = String(contact && contact.value || '').trim()
  if (!value || value.length > 500) return ''
  const type = contact && contact.type

  if (type === 'email' || (type !== 'link' && type !== 'phone' && EMAIL_RE.test(value))) {
    return EMAIL_RE.test(value) ? `mailto:${value}` : ''
  }
  if (type === 'phone' || (type !== 'link' && isPhone(value))) {
    const dial = value.replace(/[^\d+]/g, '')
    return /^\+?\d{7,15}$/.test(dial) ? `tel:${dial}` : ''
  }
  return externalHref(value)
}

function isPhone(value) {
  return /^\+?[0-9][0-9\s-]{5,18}[0-9]$/.test(value)
}

function externalHref(value) {
  let candidate = value.trim()
  if (!/^https?:\/\//i.test(candidate)) {
    if (!DOMAIN_RE.test(candidate)) return ''
    candidate = `https://${candidate}`
  }
  let url
  try {
    url = new URL(candidate)
  } catch {
    return ''
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
  if (url.username || url.password) return ''
  return url.href
}
