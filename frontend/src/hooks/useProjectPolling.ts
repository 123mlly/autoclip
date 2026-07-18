import { useCallback, useEffect, useRef, useState } from 'react'
import { GetProjectsParams, projectApi, ProjectListResult } from '../services/api'
import { Project, useProjectStore } from '../store/useProjectStore'

interface UseProjectPollingOptions {
  interval?: number
  query?: GetProjectsParams
  onProjectsUpdate?: (projects: Project[]) => void
  onPaginationUpdate?: (pagination: ProjectListResult['pagination']) => void
  /** 仅在有活跃项目时开启；全部完成后应传 false */
  enabled?: boolean
}

/**
 * 按需轮询项目列表：enabled=false 时不请求。
 * 回调用 ref 持有，避免父组件重渲染导致定时器反复重启。
 */
export const useProjectPolling = ({
  interval = 2500,
  query,
  onProjectsUpdate,
  onPaginationUpdate,
  enabled = false,
}: UseProjectPollingOptions = {}) => {
  const [isPolling, setIsPolling] = useState(false)
  const intervalRef = useRef<number | null>(null)
  const onUpdateRef = useRef(onProjectsUpdate)
  const onPaginationRef = useRef(onPaginationUpdate)
  const queryRef = useRef(query)
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now())

  useEffect(() => {
    onUpdateRef.current = onProjectsUpdate
  }, [onProjectsUpdate])

  useEffect(() => {
    onPaginationRef.current = onPaginationUpdate
  }, [onPaginationUpdate])

  useEffect(() => {
    queryRef.current = query
  }, [query])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setIsPolling(false)
  }, [])

  const applyResult = useCallback((result: ProjectListResult) => {
    onUpdateRef.current?.(result.items)
    onPaginationRef.current?.(result.pagination)
    setLastUpdateTime(Date.now())
  }, [])

  const refreshNow = useCallback(async () => {
    const result = await projectApi.getProjects(queryRef.current)
    applyResult(result)
    return result
  }, [applyResult])

  useEffect(() => {
    if (!enabled) {
      stopPolling()
      return
    }

    let cancelled = false

    const poll = async () => {
      try {
        if (useProjectStore.getState().isDragging) return
        const result = await projectApi.getProjects(queryRef.current)
        if (cancelled) return
        applyResult(result)
      } catch (error) {
        if (!cancelled) {
          console.error('Polling error:', error)
        }
      }
    }

    setIsPolling(true)
    poll()
    intervalRef.current = window.setInterval(poll, interval)

    return () => {
      cancelled = true
      stopPolling()
    }
  }, [enabled, interval, applyResult, stopPolling])

  return {
    isPolling,
    lastUpdateTime,
    stopPolling,
    refreshNow,
  }
}

export default useProjectPolling
