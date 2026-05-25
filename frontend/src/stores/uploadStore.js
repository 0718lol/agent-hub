import { create } from 'zustand'

/**
 * 上传队列 Zustand Store — 管理上传进度、队列和已上传文件列表
 */
export const useUploadStore = create((set, get) => ({
  // 上传队列：{ id, file, progress, status, result }
  queue: [],

  // 最近上传成功的文件列表
  uploadedFiles: [],

  // 添加上传任务
  addToQueue: (file) => {
    const id = `upload_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    set((s) => ({
      queue: [...s.queue, { id, file, progress: 0, status: 'pending', result: null }],
    }))
    return id
  },

  // 更新上传进度
  updateProgress: (id, progress) =>
    set((s) => ({
      queue: s.queue.map((item) =>
        item.id === id ? { ...item, progress, status: 'uploading' } : item
      ),
    })),

  // 上传完成
  markComplete: (id, result) =>
    set((s) => ({
      queue: s.queue.map((item) =>
        item.id === id ? { ...item, progress: 100, status: 'done', result } : item
      ),
      uploadedFiles: [...s.uploadedFiles, result],
    })),

  // 上传失败
  markFailed: (id, error) =>
    set((s) => ({
      queue: s.queue.map((item) =>
        item.id === id ? { ...item, status: 'error', error } : item
      ),
    })),

  // 清除已完成/失败的任务
  clearQueue: () =>
    set((s) => ({
      queue: s.queue.filter((item) => item.status === 'uploading' || item.status === 'pending'),
    })),

  // 清空已上传列表
  clearUploadedFiles: () => set({ uploadedFiles: [] }),
}))
