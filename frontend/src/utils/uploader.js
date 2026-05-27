/**
 * 文件上传工具 — 封装 FormData 上传请求
 */
import { useUploadStore } from '../stores/uploadStore'

/**
 * 上传单个文件到服务器
 * @param {File} file
 * @param {{ onProgress?: (pct: number) => void }} options
 * @returns {Promise<object>} 服务器返回的文件元数据
 */
export async function uploadFile(file, options = {}) {
  const { onProgress } = options

  const formData = new FormData()
  formData.append('file', file)

  // 使用 XMLHttpRequest 以便支持进度事件
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        const pct = Math.round((e.loaded / e.total) * 100)
        onProgress(pct)
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText)
          resolve(data)
        } catch {
          reject(new Error('解析响应失败'))
        }
      } else {
        reject(new Error(`上传失败 (${xhr.status})`))
      }
    })

    xhr.addEventListener('error', () => reject(new Error('网络错误')))
    xhr.addEventListener('abort', () => reject(new Error('上传已取消')))

    xhr.open('POST', '/api/upload')
    xhr.send(formData)
  })
}

/**
 * 便捷方法：上传文件并自动管理 Store 状态
 * @param {File} file
 * @returns {Promise<object>} 上传结果
 */
export async function uploadWithStore(file) {
  const store = useUploadStore.getState()
  const id = store.addToQueue(file)

  try {
    const result = await uploadFile(file, {
      onProgress: (pct) => useUploadStore.getState().updateProgress(id, pct),
    })
    useUploadStore.getState().markComplete(id, result)
    return result
  } catch (err) {
    useUploadStore.getState().markFailed(id, err.message)
    throw err
  }
}
