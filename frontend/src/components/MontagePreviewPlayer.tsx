import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Space, Tag, Typography } from 'antd'
import {
  CaretRightOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import { MontageSegment, projectApi } from '../services/api'
import './MontageTab.css'

const { Text } = Typography

type PreviewClipInfo = {
  segmentId: string
  title: string
  projectId: string
  clipId: string
  inOffset: number
  outOffset: number
  duration: number
}

interface MontagePreviewPlayerProps {
  segments: MontageSegment[]
  resolveSegment: (segment: MontageSegment) => {
    id: string
    title: string
    duration: number
    project_id: string
  } | undefined
  projectId: string
  aspectRatio?: string
  renderedUrl?: string | null
  activeSegmentId?: string | null
  onActiveSegmentChange?: (segmentId: string | null) => void
}

function segmentDuration(segment: MontageSegment, clipDuration: number): number {
  const inOffset = Number(segment.in_offset || 0)
  const outOffset =
    segment.out_offset === null || segment.out_offset === undefined
      ? clipDuration
      : Number(segment.out_offset)
  return Math.max(0.1, outOffset - inOffset)
}

const MontagePreviewPlayer: React.FC<MontagePreviewPlayerProps> = ({
  segments,
  resolveSegment,
  projectId,
  aspectRatio = '9:16',
  renderedUrl,
  activeSegmentId,
  onActiveSegmentChange,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [mode, setMode] = useState<'timeline' | 'rendered'>(renderedUrl ? 'rendered' : 'timeline')
  const [currentIndex, setCurrentIndex] = useState(0)
  const [playing, setPlaying] = useState(false)

  const previewItems = useMemo<PreviewClipInfo[]>(() => {
    return segments
      .map((segment) => {
        const clip = resolveSegment(segment)
        if (!clip) return null
        const clipDuration = clip.duration || 0
        const inOffset = Number(segment.in_offset || 0)
        const outOffset =
          segment.out_offset === null || segment.out_offset === undefined
            ? clipDuration
            : Number(segment.out_offset)
        return {
          segmentId: segment.id,
          title: clip.title,
          projectId: segment.project_id || clip.project_id || projectId,
          clipId: clip.id,
          inOffset,
          outOffset,
          duration: segmentDuration(segment, clipDuration),
        }
      })
      .filter(Boolean) as PreviewClipInfo[]
  }, [segments, resolveSegment, projectId])

  const currentItem = previewItems[currentIndex]

  useEffect(() => {
    if (renderedUrl) return
    setMode('timeline')
  }, [renderedUrl])

  useEffect(() => {
    if (!activeSegmentId || previewItems.length === 0) return
    const index = previewItems.findIndex((item) => item.segmentId === activeSegmentId)
    if (index >= 0) {
      setCurrentIndex(index)
      setMode('timeline')
      setPlaying(true)
    }
  }, [activeSegmentId, previewItems])

  useEffect(() => {
    setCurrentIndex((prev) => Math.min(prev, Math.max(0, previewItems.length - 1)))
  }, [previewItems.length])

  const loadCurrentSegment = useCallback(() => {
    const video = videoRef.current
    const item = previewItems[currentIndex]
    if (!video || !item || mode !== 'timeline') return

    const url = projectApi.getClipVideoUrl(item.projectId, item.clipId)
    if (video.src !== url) {
      video.src = url
    }
    const seekToStart = () => {
      try {
        video.currentTime = item.inOffset
      } catch {
        // ignore seek before metadata
      }
    }
    if (video.readyState >= 1) {
      seekToStart()
    } else {
      video.onloadedmetadata = seekToStart
    }
  }, [currentIndex, mode, previewItems])

  useEffect(() => {
    loadCurrentSegment()
  }, [loadCurrentSegment])

  useEffect(() => {
    const video = videoRef.current
    if (!video || mode !== 'timeline') return

    const onTimeUpdate = () => {
      const item = previewItems[currentIndex]
      if (!item) return
      if (video.currentTime >= item.outOffset - 0.05) {
        if (playing && currentIndex < previewItems.length - 1) {
          setCurrentIndex((prev) => prev + 1)
        } else {
          setPlaying(false)
          video.pause()
        }
      }
    }

    video.addEventListener('timeupdate', onTimeUpdate)
    return () => video.removeEventListener('timeupdate', onTimeUpdate)
  }, [currentIndex, mode, playing, previewItems])

  useEffect(() => {
    const video = videoRef.current
    if (!video || mode !== 'timeline') return
    if (playing) {
      void video.play().catch(() => setPlaying(false))
    } else {
      video.pause()
    }
  }, [playing, mode, currentIndex])

  const handleTogglePlay = () => {
    if (mode === 'rendered') {
      const video = videoRef.current
      if (!video) return
      if (video.paused) {
        void video.play()
        setPlaying(true)
      } else {
        video.pause()
        setPlaying(false)
      }
      return
    }
    if (previewItems.length === 0) return
    setPlaying((prev) => !prev)
  }

  const handlePrev = () => {
    setMode('timeline')
    setCurrentIndex((prev) => {
      const next = Math.max(0, prev - 1)
      onActiveSegmentChange?.(previewItems[next]?.segmentId ?? null)
      return next
    })
    setPlaying(true)
  }

  const handleNext = () => {
    setMode('timeline')
    setCurrentIndex((prev) => {
      const next = Math.min(previewItems.length - 1, prev + 1)
      onActiveSegmentChange?.(previewItems[next]?.segmentId ?? null)
      return next
    })
    setPlaying(true)
  }

  const isPortrait = aspectRatio !== '16:9'
  const previewHeight = isPortrait ? 360 : 220

  return (
    <div className="montage-preview-panel">
      <div className="montage-preview-toolbar">
        <Space wrap>
          <Text strong>预览</Text>
          <Button
            size="small"
            type={mode === 'timeline' ? 'primary' : 'default'}
            disabled={previewItems.length === 0}
            onClick={() => setMode('timeline')}
          >
            时间轴
          </Button>
          {renderedUrl && (
            <Button
              size="small"
              type={mode === 'rendered' ? 'primary' : 'default'}
              onClick={() => {
                setMode('rendered')
                setPlaying(false)
              }}
            >
              成片
            </Button>
          )}
          {mode === 'timeline' && currentItem && (
            <Tag>
              {currentIndex + 1}/{previewItems.length} · {currentItem.title}
            </Tag>
          )}
        </Space>
        <Space>
          {mode === 'timeline' && (
            <>
              <Button
                size="small"
                icon={<StepBackwardOutlined />}
                disabled={currentIndex <= 0}
                onClick={handlePrev}
              />
              <Button
                size="small"
                icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
                disabled={previewItems.length === 0}
                onClick={handleTogglePlay}
              />
              <Button
                size="small"
                icon={<StepForwardOutlined />}
                disabled={currentIndex >= previewItems.length - 1}
                onClick={handleNext}
              />
            </>
          )}
          {mode === 'rendered' && renderedUrl && (
            <Button
              size="small"
              icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
              onClick={handleTogglePlay}
            >
              播放成片
            </Button>
          )}
        </Space>
      </div>

      <div
        className={`montage-preview-stage${isPortrait ? ' montage-preview-stage-portrait' : ' montage-preview-stage-landscape'}`}
        style={{ height: previewHeight }}
      >
        {mode === 'rendered' && renderedUrl ? (
          <video
            ref={videoRef}
            key={`rendered-${renderedUrl}`}
            src={renderedUrl}
            controls
            className="montage-preview-video"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : previewItems.length > 0 && currentItem ? (
          <video
            ref={videoRef}
            key={`${currentItem.projectId}-${currentItem.clipId}-${currentIndex}`}
            className="montage-preview-video"
            controls
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : (
          <div className="montage-preview-empty">添加片段后可预览时间轴</div>
        )}
      </div>
    </div>
  )
}

export default MontagePreviewPlayer
