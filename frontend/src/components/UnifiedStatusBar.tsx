/**
 * 统一状态栏组件 - 替换旧的复杂进度系统
 * 支持下载中、生成字幕中、排队、处理中、完成等状态的统一显示
 */

import React, { useEffect, useRef, useState } from 'react'
import { Progress, Typography } from 'antd'
import { useSimpleProgressStore, getStageDisplayName, getStageColor, isCompleted, isFailed } from '../stores/useSimpleProgressStore'
import { apiUrl } from '../apiConfig'

const { Text } = Typography

interface UnifiedStatusBarProps {
  projectId: string
  status: string
  /** 可选：覆盖默认文案（如下载中的具体阶段） */
  statusLabel?: string
  downloadProgress?: number
  onStatusChange?: (status: string) => void
  onDownloadProgressUpdate?: (progress: number) => void
}

function StatusChip({
  percentText,
  label,
  color,
  bg,
  border,
}: {
  percentText: string
  label: string
  color: string
  bg: string
  border: string
}) {
  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: '3px',
      padding: '3px 6px',
      textAlign: 'center',
      width: '100%'
    }}>
      <div style={{
        color,
        fontSize: '11px',
        fontWeight: 600,
        lineHeight: '12px'
      }}>
        {percentText}
      </div>
      <div style={{
        color: '#999999',
        fontSize: '8px',
        lineHeight: '9px',
        minHeight: '9px'
      }}>
        {label}
      </div>
    </div>
  )
}

export const UnifiedStatusBar: React.FC<UnifiedStatusBarProps> = ({
  projectId,
  status,
  statusLabel,
  downloadProgress = 0,
  onStatusChange,
  onDownloadProgressUpdate
}) => {
  const progress = useSimpleProgressStore((s) => s.byId[projectId] ?? null)
  const startPolling = useSimpleProgressStore((s) => s.startPolling)
  const stopPolling = useSimpleProgressStore((s) => s.stopPolling)
  const [currentDownloadProgress, setCurrentDownloadProgress] = useState(downloadProgress)

  // 用 ref 持有最新回调，避免放入 effect 依赖导致无限重跑（React #185）
  const onStatusChangeRef = useRef(onStatusChange)
  const onDownloadProgressUpdateRef = useRef(onDownloadProgressUpdate)
  const statusRef = useRef(status)
  const lastEmittedStatusRef = useRef<string | null>(null)
  const lastEmittedProgressRef = useRef<number | null>(null)

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange
  }, [onStatusChange])

  useEffect(() => {
    onDownloadProgressUpdateRef.current = onDownloadProgressUpdate
  }, [onDownloadProgressUpdate])

  useEffect(() => {
    statusRef.current = status
    // 父级状态变化后，允许再次向父级同步同名状态（例如重新处理）
    if (status !== lastEmittedStatusRef.current) {
      lastEmittedStatusRef.current = status
    }
  }, [status])

  useEffect(() => {
    setCurrentDownloadProgress(downloadProgress)
    if (typeof downloadProgress === 'number') {
      lastEmittedProgressRef.current = downloadProgress
    }
  }, [downloadProgress])

  const emitStatus = (next: string) => {
    if (next === lastEmittedStatusRef.current) return
    if (next === statusRef.current) {
      lastEmittedStatusRef.current = next
      return
    }
    lastEmittedStatusRef.current = next
    onStatusChangeRef.current?.(next)
  }

  const emitProgress = (next: number) => {
    const rounded = Math.round(next)
    if (lastEmittedProgressRef.current === rounded) return
    lastEmittedProgressRef.current = rounded
    setCurrentDownloadProgress(rounded)
    onDownloadProgressUpdateRef.current?.(rounded)
  }

  // 处理中：轮询简化进度（不要把本地 isPolling 放进依赖，避免启停抖动）
  useEffect(() => {
    if (status !== 'processing') {
      return
    }

    startPolling([projectId], 2000)
    return () => {
      stopPolling([projectId])
    }
  }, [status, projectId, startPolling, stopPolling])

  // 下载 / 准备阶段：轮询项目 processing_config
  useEffect(() => {
    if (status !== 'downloading' && status !== 'preparing' && status !== 'queued') {
      return
    }

    let cancelled = false

    const pollProject = async () => {
      try {
        const response = await fetch(apiUrl(`/projects/${projectId}`))
        if (!response.ok || cancelled) return
        const projectData = await response.json()
        if (cancelled) return

        const cfg = projectData.processing_config || {}
        const newProgress = Number(cfg.download_progress ?? 0)
        const projectStatus = projectData.status
        const current = statusRef.current

        if (current === 'downloading') {
          emitProgress(newProgress)
          if (newProgress >= 100 || cfg.download_status === 'completed') {
            emitStatus(
              /字幕|Whisper|whisper/i.test(String(cfg.download_message || ''))
                ? 'preparing'
                : 'queued'
            )
          }
        }

        if (cfg.download_status === 'failed' || projectStatus === 'failed') {
          emitStatus('failed')
          return
        }
        if (projectStatus === 'processing') {
          emitStatus('processing')
          return
        }
        if (projectStatus === 'completed') {
          emitStatus('completed')
        }
      } catch (error) {
        if (!cancelled) {
          console.error('获取项目进度失败:', error)
        }
      }
    }

    pollProject()
    const interval = setInterval(pollProject, 2000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
    // 故意不依赖回调；通过 ref 读取最新值
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, projectId])

  // 进度 store 完成/失败时同步一次（用 ref + lastEmitted 防抖）
  useEffect(() => {
    if (!progress) return
    if (isCompleted(progress.stage)) {
      emitStatus('completed')
    } else if (isFailed(progress.message)) {
      emitStatus('failed')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress?.stage, progress?.message, progress?.percent])

  if (status === 'downloading') {
    const pct = Math.round(currentDownloadProgress || 0)
    return (
      <StatusChip
        percentText={`${pct}%`}
        label={statusLabel || '下载中'}
        color="#1890ff"
        bg="rgba(24, 144, 255, 0.1)"
        border="rgba(24, 144, 255, 0.3)"
      />
    )
  }

  if (status === 'preparing') {
    return (
      <StatusChip
        percentText="…"
        label={statusLabel || '生成字幕中'}
        color="#fa8c16"
        bg="rgba(250, 140, 22, 0.1)"
        border="rgba(250, 140, 22, 0.3)"
      />
    )
  }

  if (status === 'queued' || status === 'importing' || status === 'pending') {
    return (
      <StatusChip
        percentText="…"
        label={statusLabel || (status === 'importing' ? '导入中' : '排队处理中')}
        color="#faad14"
        bg="rgba(250, 173, 20, 0.1)"
        border="rgba(250, 173, 20, 0.3)"
      />
    )
  }

  if (status === 'processing') {
    if (!progress) {
      return (
        <StatusChip
          percentText="…"
          label={statusLabel || '初始化中'}
          color="#52c41a"
          bg="rgba(82, 196, 26, 0.1)"
          border="rgba(82, 196, 26, 0.3)"
        />
      )
    }

    const { stage, percent, message } = progress
    const stageDisplayName = getStageDisplayName(stage)
    const failed = isFailed(message)

    return (
      <StatusChip
        percentText={failed ? '✗ 失败' : `${percent}%`}
        label={failed ? '' : stageDisplayName}
        color={failed ? '#ff4d4f' : '#52c41a'}
        bg={failed ? 'rgba(255, 77, 79, 0.1)' : 'rgba(82, 196, 26, 0.1)'}
        border={failed ? 'rgba(255, 77, 79, 0.3)' : 'rgba(82, 196, 26, 0.3)'}
      />
    )
  }

  if (status === 'completed') {
    return (
      <StatusChip
        percentText="✓"
        label="已完成"
        color="#52c41a"
        bg="rgba(82, 196, 26, 0.1)"
        border="rgba(82, 196, 26, 0.3)"
      />
    )
  }

  if (status === 'failed') {
    return (
      <StatusChip
        percentText="✗ 失败"
        label={statusLabel && statusLabel !== '处理失败' ? statusLabel : '处理失败'}
        color="#ff4d4f"
        bg="rgba(255, 77, 79, 0.1)"
        border="rgba(255, 77, 79, 0.3)"
      />
    )
  }

  return (
    <StatusChip
      percentText="○"
      label={statusLabel || '等待处理'}
      color="#d9d9d9"
      bg="rgba(217, 217, 217, 0.1)"
      border="rgba(217, 217, 217, 0.3)"
    />
  )
}

// 简化的进度条组件 - 用于详细进度显示
interface SimpleProgressDisplayProps {
  projectId: string
  status: string
  showDetails?: boolean
}

export const SimpleProgressDisplay: React.FC<SimpleProgressDisplayProps> = ({
  projectId,
  status,
  showDetails = false
}) => {
  const { getProgress } = useSimpleProgressStore()
  const progress = getProgress(projectId)

  if (status !== 'processing' || !progress || !showDetails) {
    return null
  }

  const { stage, percent, message } = progress
  const stageDisplayName = getStageDisplayName(stage)
  const stageColor = getStageColor(stage)

  return (
    <div style={{ marginTop: '8px' }}>
      <Progress
        percent={percent}
        strokeColor={stageColor}
        showInfo={true}
        size="small"
        format={(p) => `${p}%`}
      />
      {message && (
        <Text type="secondary" style={{ fontSize: '11px', display: 'block', marginTop: '4px' }}>
          {message}
        </Text>
      )}
    </div>
  )
}
