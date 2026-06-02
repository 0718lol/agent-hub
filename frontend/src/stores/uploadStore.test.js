import { describe, it, expect, beforeEach } from 'vitest'
import { useUploadStore } from './uploadStore'

describe('uploadStore', () => {
  beforeEach(() => {
    // Reset Zustand store state before each test
    useUploadStore.setState({ queue: [], uploadedFiles: [] })
  })

  it('should initialize with empty queue and uploadedFiles list', () => {
    const state = useUploadStore.getState()
    expect(state.queue).toEqual([])
    expect(state.uploadedFiles).toEqual([])
  })

  it('should add files to the upload queue', () => {
    const store = useUploadStore.getState()
    const mockFile = new File(['dummy content'], 'test.txt', { type: 'text/plain' })
    
    const id = store.addToQueue(mockFile)
    
    const state = useUploadStore.getState()
    expect(state.queue.length).toBe(1)
    expect(state.queue[0].id).toBe(id)
    expect(state.queue[0].file).toBe(mockFile)
    expect(state.queue[0].status).toBe('pending')
  })

  it('should update upload progress', () => {
    const store = useUploadStore.getState()
    const id = store.addToQueue(new File([''], 'test.txt'))
    
    store.updateProgress(id, 45)
    
    const state = useUploadStore.getState()
    expect(state.queue[0].progress).toBe(45)
    expect(state.queue[0].status).toBe('uploading')
  })

  it('should mark upload as complete and add to uploadedFiles list', () => {
    const store = useUploadStore.getState()
    const id = store.addToQueue(new File([''], 'test.txt'))
    const mockResult = { url: '/uploads/test.txt', size: 100 }
    
    store.markComplete(id, mockResult)
    
    const state = useUploadStore.getState()
    expect(state.queue[0].status).toBe('done')
    expect(state.queue[0].progress).toBe(100)
    expect(state.queue[0].result).toEqual(mockResult)
    expect(state.uploadedFiles).toEqual([mockResult])
  })
})
