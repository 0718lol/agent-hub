// Shared inline style constants used across Settings tab components.
// These are copied verbatim from the original SettingsPanel.jsx to preserve exact visual output.

export const labelStyle = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 6,
  display: 'block',
  fontWeight: 500,
}

export const rowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 14px',
  borderRadius: 10,
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
}

export const inputStyle = {
  width: '100%',
  padding: '10px 14px',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text-primary)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'inherit',
}

export function makeBtnStyle(saving) {
  return {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: 'var(--accent)',
    border: 'none',
    color: 'white',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    opacity: saving ? 0.6 : 1,
    transition: 'all 0.2s',
  }
}
