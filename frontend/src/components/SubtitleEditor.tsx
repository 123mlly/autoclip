import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Modal, Button, Space, Tooltip, message } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  DeleteOutlined,
  UndoOutlined,
  RedoOutlined,
  SaveOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ReloadOutlined
} from '@ant-design/icons'
import ReactPlayer from 'react-player'
import { SubtitleSegment, VideoEditOperation } from '../types/subtitle'
import './SubtitleEditor.css'

interface SubtitleEditorProps {
  videoUrl: string
  subtitles: SubtitleSegment[]
  onSave: (operations: VideoEditOperation[]) => void | Promise<void>
  onClose: () => void
}

interface EditorState {
  currentTime: number
  duration: number
  playing: boolean
  selectedIds: Set<string>
  deletedSegments: Set<string>
  editHistory: VideoEditOperation[]
  historyIndex: number
  showDeleted: boolean
  saving: boolean
}

const formatTime = (seconds: number, withMs = false): string => {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  const base = hours > 0
    ? `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    : `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  if (!withMs) return base
  const ms = Math.floor((seconds % 1) * 1000)
  return `${base}.${ms.toString().padStart(3, '0')}`
}

const SubtitleEditor: React.FC<SubtitleEditorProps> = ({
  videoUrl,
  subtitles,
  onSave,
  onClose
}) => {
  const [state, setState] = useState<EditorState>({
    currentTime: 0,
    duration: 0,
    playing: false,
    selectedIds: new Set(),
    deletedSegments: new Set(),
    editHistory: [],
    historyIndex: -1,
    showDeleted: false,
    saving: false
  })

  const playerRef = useRef<ReactPlayer>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const scrubberRef = useRef<HTMLDivElement>(null)
  const segmentRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const lastClickedIndex = useRef<number>(-1)
  const [scrubbing, setScrubbing] = useState(false)

  const visibleSubtitles = useMemo(
    () => subtitles.filter(seg => state.showDeleted || !state.deletedSegments.has(seg.id)),
    [subtitles, state.showDeleted, state.deletedSegments]
  )

  const deletedDuration = useMemo(() => {
    let total = 0
    subtitles.forEach(seg => {
      if (state.deletedSegments.has(seg.id)) {
        total += Math.max(0, seg.endTime - seg.startTime)
      }
    })
    return total
  }, [subtitles, state.deletedSegments])

  const currentSegmentId = useMemo(() => {
    const hit = subtitles.find(
      seg =>
        !state.deletedSegments.has(seg.id) &&
        state.currentTime >= seg.startTime &&
        state.currentTime < seg.endTime
    )
    return hit?.id ?? null
  }, [subtitles, state.currentTime, state.deletedSegments])

  // 播放时自动滚动到当前字幕
  useEffect(() => {
    if (!currentSegmentId || !state.playing) return
    const el = segmentRefs.current.get(currentSegmentId)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentSegmentId, state.playing])

  const seekTo = useCallback((time: number) => {
    const duration = state.duration || 0
    const clamped = Math.max(0, Math.min(time, duration || time))
    playerRef.current?.seekTo(clamped, 'seconds')
    setState(prev => ({ ...prev, currentTime: clamped }))
  }, [state.duration])

  const togglePlay = useCallback(() => {
    setState(prev => ({ ...prev, playing: !prev.playing }))
  }, [])

  const seekFromClientX = useCallback((clientX: number) => {
    const el = scrubberRef.current
    if (!el || !state.duration) return
    const rect = el.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    seekTo(ratio * state.duration)
  }, [seekTo, state.duration])

  const currentSubtitleText = useMemo(() => {
    if (!currentSegmentId) return ''
    return subtitles.find(s => s.id === currentSegmentId)?.text || ''
  }, [currentSegmentId, subtitles])

  const playedPercent = state.duration > 0
    ? Math.min(100, (state.currentTime / state.duration) * 100)
    : 0

  const selectSegment = useCallback((segmentId: string, index: number, e: React.MouseEvent) => {
    setState(prev => {
      const next = new Set(prev.selectedIds)

      if (e.shiftKey && lastClickedIndex.current >= 0) {
        const start = Math.min(lastClickedIndex.current, index)
        const end = Math.max(lastClickedIndex.current, index)
        const rangeIds = visibleSubtitles.slice(start, end + 1).map(s => s.id)
        if (e.metaKey || e.ctrlKey) {
          rangeIds.forEach(id => next.add(id))
        } else {
          next.clear()
          rangeIds.forEach(id => next.add(id))
        }
      } else if (e.metaKey || e.ctrlKey) {
        if (next.has(segmentId)) next.delete(segmentId)
        else next.add(segmentId)
        lastClickedIndex.current = index
      } else {
        next.clear()
        next.add(segmentId)
        lastClickedIndex.current = index
      }

      return { ...prev, selectedIds: next }
    })
  }, [visibleSubtitles])

  const pushDelete = useCallback((segmentIds: string[]) => {
    if (segmentIds.length === 0) {
      message.warning('请先选择要删除的台词')
      return
    }

    setState(prev => {
      const toDelete = segmentIds.filter(id => !prev.deletedSegments.has(id))
      if (toDelete.length === 0) return prev

      const newDeleted = new Set([...prev.deletedSegments, ...toDelete])
      const operation: VideoEditOperation = {
        type: 'delete',
        segmentIds: toDelete,
        timestamp: Date.now()
      }
      const newHistory = [...prev.editHistory.slice(0, prev.historyIndex + 1), operation]

      return {
        ...prev,
        deletedSegments: newDeleted,
        selectedIds: new Set(),
        editHistory: newHistory,
        historyIndex: prev.historyIndex + 1
      }
    })
  }, [])

  const deleteSelected = useCallback(() => {
    setState(prev => {
      const ids = Array.from(prev.selectedIds)
      if (ids.length === 0) {
        message.warning('请先选择要删除的台词')
        return prev
      }
      const toDelete = ids.filter(id => !prev.deletedSegments.has(id))
      if (toDelete.length === 0) return prev

      const newDeleted = new Set([...prev.deletedSegments, ...toDelete])
      const operation: VideoEditOperation = {
        type: 'delete',
        segmentIds: toDelete,
        timestamp: Date.now()
      }
      const newHistory = [...prev.editHistory.slice(0, prev.historyIndex + 1), operation]

      return {
        ...prev,
        deletedSegments: newDeleted,
        selectedIds: new Set(),
        editHistory: newHistory,
        historyIndex: prev.historyIndex + 1
      }
    })
  }, [])

  const undo = useCallback(() => {
    setState(prev => {
      if (prev.historyIndex < 0) return prev
      const operation = prev.editHistory[prev.historyIndex]
      const newDeleted = new Set(prev.deletedSegments)
      if (operation.type === 'delete') {
        operation.segmentIds.forEach(id => newDeleted.delete(id))
      }
      return {
        ...prev,
        deletedSegments: newDeleted,
        historyIndex: prev.historyIndex - 1
      }
    })
  }, [])

  const redo = useCallback(() => {
    setState(prev => {
      if (prev.historyIndex >= prev.editHistory.length - 1) return prev
      const operation = prev.editHistory[prev.historyIndex + 1]
      const newDeleted = new Set(prev.deletedSegments)
      if (operation.type === 'delete') {
        operation.segmentIds.forEach(id => newDeleted.add(id))
      }
      return {
        ...prev,
        deletedSegments: newDeleted,
        historyIndex: prev.historyIndex + 1
      }
    })
  }, [])

  const resetEdits = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedIds: new Set(),
      deletedSegments: new Set(),
      editHistory: [],
      historyIndex: -1
    }))
    message.success('已重置所有编辑')
  }, [])

  const handleSave = useCallback(async () => {
    const operations = state.editHistory.slice(0, state.historyIndex + 1)
    if (operations.length === 0) {
      message.info('没有需要保存的编辑操作')
      return
    }
    setState(prev => ({ ...prev, saving: true }))
    try {
      await onSave(operations)
    } catch (error) {
      console.error('保存编辑失败:', error)
      message.error(error instanceof Error ? error.message : '保存编辑失败')
    } finally {
      setState(prev => ({ ...prev, saving: false }))
    }
  }, [state.editHistory, state.historyIndex, onSave])

  // 键盘快捷键
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      if (e.code === 'Space') {
        e.preventDefault()
        togglePlay()
        return
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
        return
      }

      if (
        ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'y') ||
        ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'z')
      ) {
        e.preventDefault()
        redo()
        return
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        handleSave()
        return
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        deleteSelected()
        return
      }

      if (e.key === 'Escape') {
        setState(prev => ({ ...prev, selectedIds: new Set() }))
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [togglePlay, undo, redo, handleSave, deleteSelected])

  const canUndo = state.historyIndex >= 0
  const canRedo = state.historyIndex < state.editHistory.length - 1
  const hasEdits = state.deletedSegments.size > 0

  return (
    <Modal
      className="subtitle-editor-modal"
      title="按台词剪辑"
      open
      onCancel={onClose}
      width={1180}
      centered
      destroyOnClose
      maskClosable={false}
      footer={
        <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
          <span className="se-footer-hint">
            点击选中 · <span className="se-kbd">⌘/Ctrl</span>多选 · <span className="se-kbd">Shift</span>连选 ·
            <span className="se-kbd">Delete</span>删除 · <span className="se-kbd">Space</span>播放
          </span>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={state.saving}
              disabled={!hasEdits}
              onClick={handleSave}
            >
              应用并导出
            </Button>
          </Space>
        </div>
      }
    >
      <div className="se-root">
        <div className="se-toolbar">
          <div className="se-toolbar-left">
            <Tooltip title="撤销 (⌘Z)">
              <Button size="small" icon={<UndoOutlined />} disabled={!canUndo} onClick={undo} />
            </Tooltip>
            <Tooltip title="重做 (⌘Y)">
              <Button size="small" icon={<RedoOutlined />} disabled={!canRedo} onClick={redo} />
            </Tooltip>
            <Tooltip title="删除选中 (Delete)">
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={state.selectedIds.size === 0}
                onClick={deleteSelected}
              >
                删除{state.selectedIds.size > 0 ? ` (${state.selectedIds.size})` : ''}
              </Button>
            </Tooltip>
            <Tooltip title="重置全部编辑">
              <Button size="small" icon={<ReloadOutlined />} disabled={!hasEdits} onClick={resetEdits}>
                重置
              </Button>
            </Tooltip>
          </div>
          <div className="se-toolbar-right">
            <span className="se-stat">
              台词 <strong>{subtitles.length}</strong>
            </span>
            <span className={`se-stat${state.deletedSegments.size ? ' danger' : ''}`}>
              已删 <strong>{state.deletedSegments.size}</strong>
              {deletedDuration > 0 ? ` · ${deletedDuration.toFixed(1)}s` : ''}
            </span>
            <Button
              size="small"
              icon={state.showDeleted ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              onClick={() => setState(prev => ({ ...prev, showDeleted: !prev.showDeleted }))}
            >
              {state.showDeleted ? '隐藏已删' : '显示已删'}
            </Button>
          </div>
        </div>

        <div className="se-body">
          <div className="se-player-pane">
            <div className="se-player-stage">
              <div
                className={`se-player-wrap${state.playing ? '' : ' is-paused'}`}
                onClick={togglePlay}
              >
                <ReactPlayer
                  ref={playerRef}
                  url={videoUrl}
                  width="100%"
                  height="100%"
                  playing={state.playing}
                  controls={false}
                  progressInterval={100}
                  onProgress={({ playedSeconds }) => {
                    if (!scrubbing) {
                      setState(prev => ({ ...prev, currentTime: playedSeconds }))
                    }
                  }}
                  onDuration={(duration) => {
                    setState(prev => ({ ...prev, duration }))
                  }}
                  onPlay={() => setState(prev => ({ ...prev, playing: true }))}
                  onPause={() => setState(prev => ({ ...prev, playing: false }))}
                  onEnded={() => setState(prev => ({ ...prev, playing: false }))}
                  config={{
                    file: {
                      attributes: {
                        controlsList: 'nodownload',
                        playsInline: true,
                        style: {
                          width: '100%',
                          height: '100%',
                          objectFit: 'contain',
                          background: '#000'
                        }
                      }
                    }
                  }}
                />
                <div className="se-play-overlay">
                  <div className="se-play-overlay-btn">
                    {state.playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                  </div>
                </div>
              </div>
            </div>
            <div className="se-current-subtitle" aria-live="polite">
              {currentSubtitleText || <span className="se-current-subtitle-empty">当前无台词</span>}
            </div>
            <div className="se-player-controls">
              <div
                ref={scrubberRef}
                className={`se-scrubber${scrubbing ? ' is-dragging' : ''}`}
                onMouseDown={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  setScrubbing(true)
                  seekFromClientX(e.clientX)

                  const onMove = (ev: MouseEvent) => seekFromClientX(ev.clientX)
                  const onUp = () => {
                    setScrubbing(false)
                    window.removeEventListener('mousemove', onMove)
                    window.removeEventListener('mouseup', onUp)
                  }
                  window.addEventListener('mousemove', onMove)
                  window.addEventListener('mouseup', onUp)
                }}
              >
                <div className="se-scrubber-track">
                  <div className="se-scrubber-played" style={{ width: `${playedPercent}%` }} />
                </div>
                <div className="se-scrubber-thumb" style={{ left: `${playedPercent}%` }} />
              </div>
              <div className="se-controls-row">
                <Space>
                  <Button
                    type="primary"
                    size="small"
                    icon={state.playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      togglePlay()
                    }}
                  >
                    {state.playing ? '暂停' : '播放'}
                  </Button>
                  <span className="se-time">
                    <span className="current">{formatTime(state.currentTime)}</span>
                    {' / '}
                    {formatTime(state.duration)}
                  </span>
                </Space>
              </div>
            </div>
          </div>

          <div className="se-list-pane">
            <div className="se-list-header">
              <h4>台词时间轴</h4>
              <span className="se-hint">按台词删除对应画面 · 双击跳转播放</span>
            </div>
            <div className="se-list" ref={listRef}>
              {visibleSubtitles.length === 0 ? (
                <div className="se-empty">
                  {subtitles.length === 0 ? '暂无台词数据' : '已删除的台词已隐藏'}
                </div>
              ) : (
                visibleSubtitles.map((segment, index) => {
                  const isDeleted = state.deletedSegments.has(segment.id)
                  const isSelected = state.selectedIds.has(segment.id)
                  const isCurrent = currentSegmentId === segment.id
                  const duration = Math.max(0, segment.endTime - segment.startTime)

                  return (
                    <div
                      key={segment.id}
                      ref={(el) => {
                        if (el) segmentRefs.current.set(segment.id, el)
                        else segmentRefs.current.delete(segment.id)
                      }}
                      className={[
                        'se-segment',
                        isCurrent ? 'is-current' : '',
                        isSelected ? 'is-selected' : '',
                        isDeleted ? 'is-deleted' : ''
                      ].filter(Boolean).join(' ')}
                      onClick={(e) => {
                        selectSegment(segment.id, index, e)
                        seekTo(segment.startTime)
                      }}
                      onDoubleClick={(e) => {
                        e.preventDefault()
                        selectSegment(segment.id, index, e)
                        seekTo(segment.startTime)
                        setState(prev => ({ ...prev, playing: true }))
                      }}
                    >
                      <div className="se-segment-index">{index + 1}</div>
                      <div className="se-segment-main">
                        <div className="se-segment-meta">
                          <span>{formatTime(segment.startTime, true)}</span>
                          <span>→</span>
                          <span>{formatTime(segment.endTime, true)}</span>
                          <span>{duration.toFixed(1)}s</span>
                        </div>
                        <div className="se-segment-text">{segment.text}</div>
                      </div>
                      <div className="se-segment-actions">
                        {!isDeleted && (
                          <Tooltip title="删除此段">
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={(e) => {
                                e.stopPropagation()
                                pushDelete([segment.id])
                              }}
                            />
                          </Tooltip>
                        )}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default SubtitleEditor
