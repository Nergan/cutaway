const BIO_MAX = 500

export function limitBioDraft(text) {
  let value = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  value = value.replace(/[ \t]+\n/g, '\n')
  value = value.replace(/\n(?:[ \t]*\n){2,}/g, '\n\n')
  value = value.replace(/^(?:[ \t]*\n)+/, '')
  if (value.length > BIO_MAX) value = value.slice(0, BIO_MAX)
  return value
}

export function normalizeBio(text) {
  return limitBioDraft(text).replace(/(?:\n[ \t]*)+$/, '').slice(0, BIO_MAX)
}

export function displayBio(text) {
  return normalizeBio(text)
}

export const BIO_LIMIT = BIO_MAX
