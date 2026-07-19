import React, { useEffect, useMemo, useState } from 'react'
import {
  Modal,
  Button,
  Space,
  Typography,
  message,
  Input,
  InputNumber,
  Popconfirm,
  Tag,
  Spin,
  Empty,
  Select,
  Upload,
  Slider,
  Switch,
  Tabs,
  Radio,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  MenuOutlined,
  PlayCircleOutlined,
  DownloadOutlined,
  ScissorOutlined,
  UploadOutlined,
  SoundOutlined,
} from '@ant-design/icons'
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd'
import { Clip } from '../store/useProjectStore'
import {
  Montage,
  MontageAudioSettings,
  MontageClipItem,
  MontageClipSources,
  MontageOutputSettings,
  MontageSegment,
  projectApi,
} from '../services/api'
import {
  MONTAGE_TRANSITION_OPTIONS,
  estimateMontageDuration,
  formatDuration,
} from '../constants/montageTransitions'
import MontagePreviewPlayer from './MontagePreviewPlayer'
import './MontageTab.css'

const { Text, Title } = Typography

type ClipLookupItem = {
  id: string
  title: string
  duration: number
  project_id: string
  project_name: string
}

function parseClipDurationFromItem(item: ClipLookupItem | Clip): number {
  if ('duration' in item && typeof item.duration === 'number' && item.duration > 0) {
    return item.duration
  }
  const clip = item as Clip
  const parseTime = (value: string) => {
    const normalized = value.replace(',', '.')
    const parts = normalized.split(':').map(Number)
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if (parts.length === 2) return parts[0] * 60 + parts[1]
    return Number(normalized) || 0
  }
  if (clip.start_time && clip.end_time) {
    return Math.max(0, parseTime(clip.end_time) - parseTime(clip.start_time))
  }
  return 0
}

function createSegment(clip: ClipLookupItem): MontageSegment {
  return {
    id: `seg-${crypto.randomUUID()}`,
    clip_id: clip.id,
    project_id: clip.project_id,
    in_offset: 0,
    out_offset: null,
    transition: 'none',
    transition_duration: 0.5,
  }
}

interface MontageEditorModalProps {
  visible: boolean
  montage: Montage | null
  clips: Clip[]
  projectId: string
  onClose: () => void
  onUpdated: (montage: Montage) => void
}

const MontageEditorModal: React.FC<MontageEditorModalProps> = ({
  visible,
  montage,
  clips,
  projectId,
  onClose,
  onUpdated,
}) => {
  const [name, setName] = useState('')
  const [segments, setSegments] = useState<MontageSegment[]>([])
  const [audio, setAudio] = useState<MontageAudioSettings>({
    bgm_volume: 0.25,
    keep_original: true,
  })
  const [output, setOutput] = useState<MontageOutputSettings>({ aspect_ratio: '9:16' })
  const [clipSources, setClipSources] = useState<MontageClipSources | null>(null)
  const [clipPoolTab, setClipPoolTab] = useState<'current' | 'other'>('current')
  const [selectedOtherProjectId, setSelectedOtherProjectId] = useState<string>()
  const [saving, setSaving] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [uploadingBgm, setUploadingBgm] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [activePreviewSegmentId, setActivePreviewSegmentId] = useState<string | null>(null)

  const clipLookup = useMemo(() => {
    const map = new Map<string, ClipLookupItem>()
    const addItem = (item: MontageClipItem) => {
      map.set(`${item.project_id}:${item.id}`, {
        id: item.id,
        title: item.title,
        duration: item.duration,
        project_id: item.project_id,
        project_name: item.project_name,
      })
    }
    clips.forEach((clip) => {
      map.set(`${projectId}:${clip.id}`, {
        id: clip.id,
        title: clip.generated_title || clip.title || '未命名切片',
        duration: parseClipDurationFromItem(clip),
        project_id: projectId,
        project_name: '当前项目',
      })
    })
    if (clipSources) {
      clipSources.current_project.clips.forEach(addItem)
      clipSources.other_projects.forEach((group) => group.clips.forEach(addItem))
    }
    return map
  }, [clipSources, clips, projectId])

  const resolveClip = (segment: MontageSegment): ClipLookupItem | undefined => {
    const pid = segment.project_id || projectId
    return clipLookup.get(`${pid}:${segment.clip_id}`)
  }

  useEffect(() => {
    if (!visible || !montage) return
    setName(montage.name)
    setSegments(montage.timeline?.segments || [])
    setAudio({
      bgm_volume: montage.timeline?.audio?.bgm_volume ?? 0.25,
      keep_original: montage.timeline?.audio?.keep_original ?? true,
      bgm_path: montage.timeline?.audio?.bgm_path,
      bgm_filename: montage.timeline?.audio?.bgm_filename,
    })
    setOutput({
      aspect_ratio: montage.timeline?.output?.aspect_ratio || '9:16',
    })
    if (montage.status === 'completed') {
      setPreviewUrl(projectApi.getMontageVideoUrl(projectId, montage.id))
    } else {
      setPreviewUrl(null)
    }
    setActivePreviewSegmentId(null)
  }, [visible, montage, projectId])

  useEffect(() => {
    if (!visible) return
    void projectApi.getMontageClipSources(projectId).then(setClipSources).catch(console.error)
  }, [visible, projectId])

  const poolClips = useMemo(() => {
    if (!clipSources) {
      return clips.map((clip) => ({
        id: clip.id,
        title: clip.generated_title || clip.title || '未命名切片',
        duration: parseClipDurationFromItem(clip),
        project_id: projectId,
        project_name: '当前项目',
      }))
    }
    if (clipPoolTab === 'current') {
      return clipSources.current_project.clips.map((item) => ({
        id: item.id,
        title: item.title,
        duration: item.duration,
        project_id: item.project_id,
        project_name: item.project_name,
      }))
    }
    const group =
      clipSources.other_projects.find((g) => g.project_id === selectedOtherProjectId) ||
      clipSources.other_projects[0]
    return (group?.clips || []).map((item) => ({
      id: item.id,
      title: item.title,
      duration: item.duration,
      project_id: item.project_id,
      project_name: item.project_name,
    }))
  }, [clipPoolTab, clipSources, clips, projectId, selectedOtherProjectId])

  const otherProjectOptions = useMemo(
    () =>
      (clipSources?.other_projects || []).map((group) => ({
        label: `${group.project_name} (${group.clips.length})`,
        value: group.project_id,
      })),
    [clipSources]
  )

  const clipDurationMap = useMemo(() => {
    const map = new Map<string, number>()
    clipLookup.forEach((clip, key) => {
      map.set(key, clip.duration || parseClipDurationFromItem(clip))
    })
    return map
  }, [clipLookup])

  const estimatedDuration = useMemo(
    () =>
      estimateMontageDuration(
        segments,
        clipDurationMap,
        (segment) => `${segment.project_id || projectId}:${segment.clip_id}`
      ),
    [segments, clipDurationMap, projectId]
  )

  useEffect(() => {
    if (clipPoolTab === 'other' && !selectedOtherProjectId && otherProjectOptions.length > 0) {
      setSelectedOtherProjectId(otherProjectOptions[0].value)
    }
  }, [clipPoolTab, otherProjectOptions, selectedOtherProjectId])

  const handleDragEnd = (result: DropResult) => {
    if (!result.destination) return
    const next = Array.from(segments)
    const [removed] = next.splice(result.source.index, 1)
    next.splice(result.destination.index, 0, removed)
    setSegments(next)
  }

  const handleAddClip = (clip: ClipLookupItem) => {
    setSegments((prev) => [...prev, createSegment(clip)])
  }

  const handleRemoveSegment = (segmentId: string) => {
    setSegments((prev) => prev.filter((s) => s.id !== segmentId))
  }

  const handleSegmentChange = (
    segmentId: string,
    field: keyof MontageSegment,
    value: string | number | null
  ) => {
    setSegments((prev) =>
      prev.map((segment) => (segment.id === segmentId ? { ...segment, [field]: value } : segment))
    )
  }

  const buildTimelinePayload = () => ({
    segments: segments.map((segment) => ({
      ...segment,
      project_id: segment.project_id || projectId,
      in_offset: Number(segment.in_offset || 0),
      out_offset:
        segment.out_offset === null || segment.out_offset === undefined
          ? null
          : Number(segment.out_offset),
      transition: segment.transition || 'none',
      transition_duration: Number(segment.transition_duration ?? 0.5),
    })),
    audio: {
      ...audio,
      bgm_volume: Number(audio.bgm_volume ?? 0.25),
      keep_original: audio.keep_original !== false,
    },
    output: {
      aspect_ratio: output.aspect_ratio === '16:9' ? '16:9' : '9:16',
    },
  })

  const handleSave = async () => {
    if (!montage) return
    if (!name.trim()) {
      message.warning('请输入混剪名称')
      return
    }
    setSaving(true)
    try {
      const updated = await projectApi.updateMontage(montage.id, {
        name: name.trim(),
        timeline: buildTimelinePayload(),
      })
      onUpdated(updated)
      message.success('混剪已保存')
    } catch (error) {
      message.error('保存失败')
      console.error(error)
    } finally {
      setSaving(false)
    }
  }

  const handleUploadBgm = async (file: File) => {
    if (!montage) return false
    setUploadingBgm(true)
    try {
      const updated = await projectApi.uploadMontageBgm(montage.id, file)
      onUpdated(updated)
      setAudio({
        bgm_volume: updated.timeline?.audio?.bgm_volume ?? 0.25,
        keep_original: updated.timeline?.audio?.keep_original ?? true,
        bgm_path: updated.timeline?.audio?.bgm_path,
        bgm_filename: updated.timeline?.audio?.bgm_filename,
      })
      message.success('BGM 已上传')
    } catch (error) {
      message.error('BGM 上传失败')
      console.error(error)
    } finally {
      setUploadingBgm(false)
    }
    return false
  }

  const pollMontageStatus = async (montageId: string): Promise<Montage> => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const current = await projectApi.getMontage(montageId)
      if (current.status === 'completed' || current.status === 'failed') {
        return current
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000))
    }
    throw new Error('渲染超时，请稍后在混剪列表中查看状态')
  }

  const handleRender = async () => {
    if (!montage) return
    if (segments.length === 0) {
      message.warning('请至少添加一个片段')
      return
    }
    setRendering(true)
    try {
      await projectApi.updateMontage(montage.id, {
        name: name.trim(),
        timeline: buildTimelinePayload(),
      })
      await projectApi.renderMontage(montage.id)
      const updated = await pollMontageStatus(montage.id)
      onUpdated(updated)
      if (updated.status === 'completed') {
        setPreviewUrl(projectApi.getMontageVideoUrl(projectId, updated.id))
        message.success('混剪渲染完成')
      } else {
        message.error(updated.error_message || '渲染失败')
      }
    } catch (error: unknown) {
      const errMsg = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      message.error(typeof errMsg === 'string' ? errMsg : '渲染失败')
      console.error(error)
    } finally {
      setRendering(false)
    }
  }

  const handleDownload = async () => {
    if (!montage) return
    setDownloading(true)
    try {
      const blob = await projectApi.downloadMontage(projectId, montage.id)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${name || montage.name || 'montage'}.mp4`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      message.error('下载失败')
      console.error(error)
    } finally {
      setDownloading(false)
    }
  }

  const handlePreviewSegment = (segmentId: string) => {
    setActivePreviewSegmentId(segmentId)
  }

  const statusTag = (status: Montage['status']) => {
    const map = {
      draft: { color: 'default', label: '草稿' },
      rendering: { color: 'processing', label: '渲染中' },
      completed: { color: 'success', label: '已完成' },
      failed: { color: 'error', label: '失败' },
    }
    const item = map[status] || map.draft
    return <Tag color={item.color}>{item.label}</Tag>
  }

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      width={1040}
      title={
        <Space>
          <ScissorOutlined />
          <span>混剪编辑</span>
          {montage && statusTag(montage.status)}
        </Space>
      }
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          {montage?.status === 'completed' && (
            <Button icon={<DownloadOutlined />} loading={downloading} onClick={handleDownload}>
              下载成片
            </Button>
          )}
          <Button loading={saving} onClick={handleSave}>
            保存
          </Button>
          <Button type="primary" loading={rendering} onClick={handleRender}>
            渲染混剪
          </Button>
        </Space>
      }
      destroyOnClose
    >
      {!montage ? (
        <Empty description="未选择混剪" />
      ) : (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary">混剪名称</Text>
            <Input value={name} onChange={(e) => setName(e.target.value)} style={{ marginTop: 6 }} />
          </div>

          <div
            style={{
              marginBottom: 16,
              padding: 12,
              borderRadius: 10,
              border: '1px solid #e3e9ef',
              background: '#fafbfc',
            }}
          >
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              输出尺寸
            </Text>
            <Radio.Group
              value={output.aspect_ratio || '9:16'}
              onChange={(e) => setOutput({ aspect_ratio: e.target.value })}
            >
              <Radio.Button value="9:16">竖屏 9:16 (1080×1920)</Radio.Button>
              <Radio.Button value="16:9">横屏 16:9 (1920×1080)</Radio.Button>
            </Radio.Group>
          </div>

          <div
            style={{
              marginBottom: 16,
              padding: 12,
              borderRadius: 10,
              border: '1px solid #e3e9ef',
              background: '#fafbfc',
            }}
          >
            <Space align="center" style={{ marginBottom: 10 }}>
              <SoundOutlined />
              <Text strong>背景音乐</Text>
            </Space>
            <Space wrap align="center" style={{ width: '100%' }}>
              <Upload beforeUpload={handleUploadBgm} showUploadList={false} accept="audio/*">
                <Button icon={<UploadOutlined />} loading={uploadingBgm}>
                  上传 BGM
                </Button>
              </Upload>
              {audio.bgm_filename && <Tag color="blue">{audio.bgm_filename}</Tag>}
              <span style={{ minWidth: 180 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  BGM 音量
                </Text>
                <Slider
                  min={0}
                  max={1}
                  step={0.05}
                  value={audio.bgm_volume ?? 0.25}
                  onChange={(value) => setAudio((prev) => ({ ...prev, bgm_volume: value }))}
                />
              </span>
              <Space>
                <Text type="secondary">保留原声</Text>
                <Switch
                  checked={audio.keep_original !== false}
                  onChange={(checked) => setAudio((prev) => ({ ...prev, keep_original: checked }))}
                />
              </Space>
            </Space>
          </div>

          <MontagePreviewPlayer
            segments={segments}
            resolveSegment={resolveClip}
            projectId={projectId}
            aspectRatio={output.aspect_ratio || '9:16'}
            renderedUrl={previewUrl}
            activeSegmentId={activePreviewSegmentId}
            onActiveSegmentChange={setActivePreviewSegmentId}
          />

          {montage.error_message && montage.status === 'failed' && (
            <div style={{ marginBottom: 12 }}>
              <Text type="danger">{montage.error_message}</Text>
            </div>
          )}

          <div className="montage-editor-layout">
            <div className="montage-clip-pool">
              <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
                切片库
              </Title>
              <Tabs
                size="small"
                activeKey={clipPoolTab}
                onChange={(key) => setClipPoolTab(key as 'current' | 'other')}
                items={[
                  { key: 'current', label: '当前项目' },
                  { key: 'other', label: '其他项目' },
                ]}
              />
              {clipPoolTab === 'other' && (
                <Select
                  style={{ width: '100%', marginBottom: 10 }}
                  placeholder="选择项目"
                  options={otherProjectOptions}
                  value={selectedOtherProjectId}
                  onChange={setSelectedOtherProjectId}
                />
              )}
              {poolClips.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用切片" />
              ) : (
                poolClips.map((clip) => (
                  <div key={`${clip.project_id}:${clip.id}`} className="montage-clip-item">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="montage-segment-title">{clip.title}</div>
                      <div className="montage-segment-meta">
                        {clip.project_name} · {Math.round(clip.duration || 0)}s
                      </div>
                    </div>
                    <Button
                      size="small"
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => handleAddClip(clip)}
                    >
                      添加
                    </Button>
                  </div>
                ))
              )}
            </div>

            <div className="montage-timeline">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 12,
                }}
              >
                <Title level={5} style={{ margin: 0 }}>
                  时间轴 ({segments.length})
                </Title>
                {segments.length > 0 && (
                  <Tag color="processing">预计 {formatDuration(estimatedDuration)}</Tag>
                )}
              </div>

              {segments.length === 0 ? (
                <Empty
                  image={<PlayCircleOutlined style={{ fontSize: 40, color: '#b8c4d1' }} />}
                  description="从左侧添加切片到时间轴"
                />
              ) : (
                <DragDropContext onDragEnd={handleDragEnd}>
                  <Droppable droppableId="montage-timeline">
                    {(provided) => (
                      <div ref={provided.innerRef} {...provided.droppableProps}>
                        {segments.map((segment, index) => {
                          const clip = resolveClip(segment)
                          const duration = clip ? parseClipDurationFromItem(clip) : 0
                          return (
                            <Draggable key={segment.id} draggableId={segment.id} index={index}>
                              {(dragProvided, snapshot) => (
                                <div
                                  ref={dragProvided.innerRef}
                                  {...dragProvided.draggableProps}
                                  className={`montage-segment${snapshot.isDragging ? ' dragging' : ''}${
                                    activePreviewSegmentId === segment.id ? ' active-preview' : ''
                                  }`}
                                >
                                  <div
                                    {...dragProvided.dragHandleProps}
                                    style={{ color: '#6b7585', cursor: 'grab' }}
                                  >
                                    <MenuOutlined />
                                  </div>
                                  <div className="montage-segment-index">{index + 1}</div>
                                  <div className="montage-segment-main">
                                    <div className="montage-segment-title">
                                      {clip?.title || segment.clip_id}
                                    </div>
                                    <div className="montage-segment-meta">
                                      {clip?.project_name || '未知项目'}
                                    </div>
                                    <Space size={8} wrap style={{ marginTop: 6 }}>
                                      <span>
                                        <Text type="secondary" style={{ fontSize: 11 }}>
                                          入点
                                        </Text>
                                        <InputNumber
                                          size="small"
                                          min={0}
                                          max={duration || undefined}
                                          step={0.1}
                                          value={segment.in_offset}
                                          onChange={(value) =>
                                            handleSegmentChange(segment.id, 'in_offset', value ?? 0)
                                          }
                                          style={{ width: 72, marginLeft: 4 }}
                                        />
                                      </span>
                                      <span>
                                        <Text type="secondary" style={{ fontSize: 11 }}>
                                          出点
                                        </Text>
                                        <InputNumber
                                          size="small"
                                          min={segment.in_offset || 0}
                                          max={duration || undefined}
                                          step={0.1}
                                          value={segment.out_offset ?? undefined}
                                          placeholder="整段"
                                          onChange={(value) =>
                                            handleSegmentChange(segment.id, 'out_offset', value)
                                          }
                                          style={{ width: 72, marginLeft: 4 }}
                                        />
                                      </span>
                                      {index > 0 && (
                                        <>
                                          <Select
                                            size="small"
                                            value={segment.transition || 'none'}
                                            style={{ width: 108 }}
                                            options={MONTAGE_TRANSITION_OPTIONS.map((item) => ({
                                              value: item.value,
                                              label: item.label,
                                            }))}
                                            onChange={(value) =>
                                              handleSegmentChange(segment.id, 'transition', value)
                                            }
                                          />
                                          {segment.transition && segment.transition !== 'none' && (
                                            <InputNumber
                                              size="small"
                                              min={0.1}
                                              max={3}
                                              step={0.1}
                                              value={segment.transition_duration ?? 0.5}
                                              onChange={(value) =>
                                                handleSegmentChange(
                                                  segment.id,
                                                  'transition_duration',
                                                  value ?? 0.5
                                                )
                                              }
                                              addonBefore="转场"
                                              style={{ width: 120 }}
                                            />
                                          )}
                                        </>
                                      )}
                                    </Space>
                                  </div>
                                  <Button
                                    size="small"
                                    icon={<PlayCircleOutlined />}
                                    onClick={() => handlePreviewSegment(segment.id)}
                                  />
                                  <Popconfirm
                                    title="移除此片段？"
                                    onConfirm={() => handleRemoveSegment(segment.id)}
                                  >
                                    <Button size="small" danger icon={<DeleteOutlined />} />
                                  </Popconfirm>
                                </div>
                              )}
                            </Draggable>
                          )
                        })}
                        {provided.placeholder}
                      </div>
                    )}
                  </Droppable>
                </DragDropContext>
              )}
            </div>
          </div>

          {(saving || rendering) && (
            <div style={{ marginTop: 12 }}>
              <Spin size="small" />{' '}
              <Text type="secondary">{rendering ? '正在渲染，请稍候…' : '保存中…'}</Text>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

export default MontageEditorModal
