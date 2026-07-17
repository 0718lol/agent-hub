'use strict'

const ci = require('miniprogram-ci')

async function main() {
  const [action, projectPath, appid, privateKeyPath, version, desc, qrcodeOutputDest] = process.argv.slice(2)
  const project = new ci.Project({
    appid,
    type: 'miniProgram',
    projectPath,
    privateKeyPath,
    ignores: ['node_modules/**/*', '.git/**/*'],
  })
  const onProgressUpdate = (progress) => {
    const message = progress && (progress.message || progress.status)
    if (message) process.stdout.write(`${String(message)}\n`)
  }
  if (action === 'preview') {
    if (!qrcodeOutputDest) throw new Error('Missing preview QR code destination')
    await ci.preview({
      project,
      desc,
      setting: { useProjectConfig: true },
      robot: 1,
      threads: 2,
      qrcodeFormat: 'image',
      qrcodeOutputDest,
      onProgressUpdate,
    })
    process.stdout.write('MINIPROGRAM_PREVIEW_SUCCESS\n')
    return
  }
  if (action !== 'upload') throw new Error(`Unsupported action: ${action}`)
  await ci.upload({
    project, version, desc,
    setting: { useProjectConfig: true },
    robot: 1,
    threads: 2,
    onProgressUpdate,
  })
  process.stdout.write('MINIPROGRAM_UPLOAD_SUCCESS\n')
}

main().catch((error) => {
  process.stderr.write(`${error && error.message ? error.message : String(error)}\n`)
  process.exit(1)
})
