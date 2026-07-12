import type { Project } from '../store/useProjectStore'

/** 卡片上展示用的细分状态（比后端 pending 更细） */
export type CardDisplayStatus =
  | 'downloading'
  | 'preparing'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'pending'

export interface ProjectCardDisplay {
  status: CardDisplayStatus
  /** 有真实进度时返回 0–100；字幕/排队等无进度时为 null */
  percent: number | null
  label: string
}

function clipLabel(message: string, fallback: string, max = 10): string {
  const t = message.trim()
  if (!t) return fallback
  return t.length > max ? `${t.slice(0, max)}…` : t
}

/**
 * 根据项目 status + processing_config 解析卡片展示文案与进度。
 * 避免把所有 pending 都显示成「导入中」和假 20%。
 */
export function resolveProjectCardDisplay(project: Project): ProjectCardDisplay {
  const cfg = project.processing_config || {}
  const dlStatus = String(cfg.download_status || '')
  const dlProgress = Number(cfg.download_progress ?? 0)
  const dlMessage = String(cfg.download_message || '')
  const projectStatus = project.status === 'error' ? 'failed' : project.status

  if (projectStatus === 'failed' || dlStatus === 'failed') {
    return {
      status: 'failed',
      percent: null,
      label: clipLabel(dlMessage, '处理失败', 12),
    }
  }

  if (projectStatus === 'completed') {
    return { status: 'completed', percent: 100, label: '已完成' }
  }

  if (projectStatus === 'processing') {
    const stepPercent =
      project.current_step && project.total_steps
        ? Math.round((project.current_step / project.total_steps) * 100)
        : null
    return {
      status: 'processing',
      percent: stepPercent,
      label: '处理中',
    }
  }

  // pending：按下载 / 字幕 / 排队细分
  const isDownloading =
    dlStatus === 'downloading' ||
    (dlProgress > 0 && dlProgress < 100 && dlStatus !== 'completed')

  if (isDownloading) {
    return {
      status: 'downloading',
      percent: Math.min(99, Math.max(0, Math.round(dlProgress))),
      label: clipLabel(dlMessage, '下载中'),
    }
  }

  const preparingHint =
    /字幕|Whisper|whisper|缩略图|整理文件|生成字幕/i.test(dlMessage) ||
    dlStatus === 'preparing'

  if (preparingHint || (dlStatus === 'completed' && /字幕|处理/.test(dlMessage))) {
    // 下载已完成、后台在做 Whisper/整理：无可靠百分比
    return {
      status: 'preparing',
      percent: null,
      label: /字幕|Whisper|whisper/i.test(dlMessage) ? '生成字幕中' : clipLabel(dlMessage, '准备中'),
    }
  }

  if (dlStatus === 'completed' || dlProgress >= 100) {
    return { status: 'queued', percent: null, label: '排队处理中' }
  }

  // 本地上传等：尚无 download 字段
  if (/上传|导入/.test(dlMessage)) {
    return {
      status: 'preparing',
      percent: null,
      label: clipLabel(dlMessage, '导入中'),
    }
  }

  return { status: 'queued', percent: null, label: '等待处理' }
}

export function isBusyCardStatus(status: CardDisplayStatus): boolean {
  return (
    status === 'downloading' ||
    status === 'preparing' ||
    status === 'queued' ||
    status === 'processing'
  )
}
