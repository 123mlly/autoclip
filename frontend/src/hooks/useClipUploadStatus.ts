import { useCallback, useEffect, useRef, useState } from 'react'
import { uploadApi } from '../services/uploadApi'
import { youtubeUploadApi } from '../services/youtubeUploadApi'
import {
  buildClipUploadStatusMap,
  ClipUploadStatusMap,
  hasActiveUploads,
} from '../utils/clipUploadStatus'

export function useClipUploadStatus(projectId?: string) {
  const [statusMap, setStatusMap] = useState<ClipUploadStatusMap>({})
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const [bilibiliRecords, youtubeRecords] = await Promise.all([
        uploadApi.getUploadRecords(projectId),
        youtubeUploadApi.getUploadRecords(projectId),
      ])
      if (!mountedRef.current) return
      setStatusMap(buildClipUploadStatusMap(bilibiliRecords, youtubeRecords))
    } catch (error) {
      console.error('获取切片投稿状态失败:', error)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => {
      mountedRef.current = false
    }
  }, [refresh])

  useEffect(() => {
    if (!hasActiveUploads(statusMap)) return
    const timer = window.setInterval(refresh, 4000)
    return () => window.clearInterval(timer)
  }, [statusMap, refresh])

  return { statusMap, refresh, loading }
}
