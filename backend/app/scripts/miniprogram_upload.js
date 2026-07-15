'use strict'

const ci = require('miniprogram-ci')

async function main() {
  const [projectPath, appid, privateKeyPath, version, desc] = process.argv.slice(2)
  const project = new ci.Project({
    appid,
    type: 'miniProgram',
    projectPath,
    privateKeyPath,
    ignores: ['node_modules/**/*', '.git/**/*'],
  })
  await ci.upload({
    project,
    version,
    desc,
    setting: { useProjectConfig: true },
    robot: 1,
    threads: 2,
    onProgressUpdate: (progress) => {
      const message = progress && (progress.message || progress.status)
      if (message) process.stdout.write(`${String(message)}\n`)
    },
  })
  process.stdout.write('MINIPROGRAM_UPLOAD_SUCCESS\n')
}

main().catch((error) => {
  process.stderr.write(`${error && error.message ? error.message : String(error)}\n`)
  process.exit(1)
})
