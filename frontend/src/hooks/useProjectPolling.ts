import { useCallback, useEffect, useRef, useState } from 'react'
import { projectApi } from '../services/api'
import { Project, useProjectStore } from '../store/useProjectStore'

interface UseProjectPollingOptions {
  interval?: number
  onProjectsUpdate?: (projects: Project[]) => void
  /** 仅在有活跃项目时开启；全部完成后应传 false */
  enabled?: boolean
}

/**
 * 按需轮询项目列表：enabled=false 时不请求。
 * 回调用 ref 持有，避免父组件重渲染导致定时器反复重启。
 */
export const useProjectPolling = ({
  interval = 2500,
  onProjectsUpdate,
  enabled = false
}: UseProjectPollingOptions = {}) => {
  const [isPolling, setIsPolling] = useState(false)
  const intervalRef = useRef<number | null>(null)
  const onUpdateRef = useRef(onProjectsUpdate)
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now())

  useEffect(() => {
    onUpdateRef.current = onProjectsUpdate
  }, [onProjectsUpdate])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setIsPolling(false)
  }, [])

  const applyProjects = useCallback((projects: Project[]) => {
    onUpdateRef.current?.(projects)
    setLastUpdateTime(Date.now())
  }, [])

  const refreshNow = useCallback(async () => {
    const projects = await projectApi.getProjects()
    applyProjects(projects || [])
    return projects
  }, [applyProjects])

  useEffect(() => {
    if (!enabled) {
      stopPolling()
      return
    }

    let cancelled = false

    const poll = async () => {
      try {
        if (useProjectStore.getState().isDragging) return
        const projects = await projectApi.getProjects()
        if (cancelled) return
        applyProjects(projects || [])
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
  }, [enabled, interval, applyProjects, stopPolling])

  return {
    isPolling,
    lastUpdateTime,
    stopPolling,
    refreshNow
  }
}

export default useProjectPolling
