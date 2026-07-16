import React from 'react'
import { Tooltip } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  ClipUploadStatus,
  getBilibiliVideoUrl,
  isUploadSuccess,
  PlatformUploadStatus,
} from '../utils/clipUploadStatus'

interface ClipUploadBadgesProps {
  uploadStatus?: ClipUploadStatus
}

const PLATFORM_LABELS = {
  bilibili: 'B站',
  youtube: 'YouTube',
} as const

type StatusStyle = {
  color: string
  background: string
  border: string
  icon: React.ReactNode
  text: string
}

function getStatusStyle(status: string): StatusStyle {
  if (isUploadSuccess(status)) {
    return {
      color: '#0e7c66',
      background: 'rgba(14, 124, 102, 0.08)',
      border: 'rgba(14, 124, 102, 0.28)',
      icon: <CheckCircleOutlined />,
      text: '已完成',
    }
  }
  if (status === 'processing') {
    return {
      color: '#1677ff',
      background: 'rgba(22, 119, 255, 0.08)',
      border: 'rgba(22, 119, 255, 0.28)',
      icon: <LoadingOutlined spin />,
      text: '上传中',
    }
  }
  if (status === 'pending') {
    return {
      color: '#6b7585',
      background: 'rgba(107, 117, 133, 0.08)',
      border: 'rgba(107, 117, 133, 0.22)',
      icon: <ClockCircleOutlined />,
      text: '排队中',
    }
  }
  if (status === 'failed') {
    return {
      color: '#d4380d',
      background: 'rgba(212, 56, 13, 0.06)',
      border: 'rgba(212, 56, 13, 0.22)',
      icon: <CloseCircleOutlined />,
      text: '失败',
    }
  }
  if (status === 'cancelled') {
    return {
      color: '#8c8c8c',
      background: 'rgba(140, 140, 140, 0.08)',
      border: 'rgba(140, 140, 140, 0.2)',
      icon: <StopOutlined />,
      text: '已取消',
    }
  }
  return {
    color: '#6b7585',
    background: 'rgba(107, 117, 133, 0.08)',
    border: 'rgba(107, 117, 133, 0.22)',
    icon: null,
    text: status,
  }
}

function getVideoLink(item: PlatformUploadStatus): string | undefined {
  if (item.platform === 'bilibili') {
    return getBilibiliVideoUrl(item.bvid)
  }
  return item.video_url
}

function PlatformTag({ item }: { item: PlatformUploadStatus }) {
  const label = PLATFORM_LABELS[item.platform]
  const style = getStatusStyle(item.status)
  const link = getVideoLink(item)
  const clickable = Boolean(link && isUploadSuccess(item.status))
  const progressText =
    item.status === 'processing' && item.progress > 0 ? ` ${item.progress}%` : ''

  const tooltipTitle = (
    <div>
      <div>
        {label} · {style.text}
        {progressText}
      </div>
      {item.error_message && <div style={{ marginTop: 4 }}>{item.error_message}</div>}
      {clickable && <div style={{ marginTop: 4, fontSize: 11 }}>点击打开视频</div>}
    </div>
  )

  return (
    <Tooltip title={tooltipTitle}>
      <span
        className={`clip-upload-status-tag${clickable ? ' clip-upload-status-tag--clickable' : ''}`}
        style={{
          color: style.color,
          background: style.background,
          border: `1px solid ${style.border}`,
        }}
        onClick={(e) => {
          if (clickable && link) {
            e.stopPropagation()
            window.open(link, '_blank', 'noopener,noreferrer')
          }
        }}
      >
        <span className="clip-upload-status-tag__icon">{style.icon}</span>
        <span>
          {label} · {style.text}
          {progressText}
        </span>
      </span>
    </Tooltip>
  )
}

const ClipUploadBadges: React.FC<ClipUploadBadgesProps> = ({ uploadStatus }) => {
  if (!uploadStatus?.bilibili && !uploadStatus?.youtube) return null

  return (
    <div className="clip-upload-status-row">
      {uploadStatus.bilibili && <PlatformTag item={uploadStatus.bilibili} />}
      {uploadStatus.youtube && <PlatformTag item={uploadStatus.youtube} />}
    </div>
  )
}

export default ClipUploadBadges
