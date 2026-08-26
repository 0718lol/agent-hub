const INTERNAL_NOISE_PATTERNS = [
  /输出格式不符合要求/i,
  /missing expected content/i,
  /正在重新生成\.\.\./,
]

export function getMessageText(message) {
  const text = message?.content?.text
  return typeof text === 'string' ? text : ''
}

export function isInternalNoiseMessage(message) {
  const text = getMessageText(message)
  return text.length > 0 && INTERNAL_NOISE_PATTERNS.some((pattern) => pattern.test(text))
}
