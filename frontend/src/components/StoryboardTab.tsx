import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
  Popconfirm,
  Spin,
} from 'antd'
import {
  RobotOutlined,
  SendOutlined,
  DownloadOutlined,
  DeleteOutlined,
  VideoCameraOutlined,
  ArrowLeftOutlined,
  EditOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { Storyboard, StoryboardShot, projectApi } from '../services/api'
import './StoryboardTab.css'

const { Title, Text } = Typography
const { TextArea } = Input

interface StoryboardTabProps {
  projectId: string
  embedded?: boolean
}

const statusMap: Record<
  Storyboard['status'],
  { color: string; text: string }
> = {
  draft: { color: 'default', text: '草稿' },
  generating: { color: 'processing', text: '生成中' },
  ready: { color: 'blue', text: '待渲染' },
  rendering: { color: 'processing', text: '渲染中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(2).padStart(m > 0 ? 5 : 2, '0')
  return m > 0 ? `${m}:${s}` : s
}

const StoryboardTab: React.FC<StoryboardTabProps> = ({ projectId, embedded = false }) => {
  const [storyboards, setStoryboards] = useState<Storyboard[]>([])
  const [active, setActive] = useState<Storyboard | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [saving, setSaving] = useState(false)

  const [customPrompt, setCustomPrompt] = useState('')
  const [durationRatio, setDurationRatio] = useState(0.5)
  const [aspectRatio, setAspectRatio] = useState<'9:16' | '16:9'>('9:16')
  const [sceneAlign, setSceneAlign] = useState(true)
  const [subtitleAlign, setSubtitleAlign] = useState(true)
  const [goldenOpening, setGoldenOpening] = useState(true)
  const [maxShots, setMaxShots] = useState(16)
  const [editedShots, setEditedShots] = useState<StoryboardShot[]>([])
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const loadStoryboards = useCallback(async () => {
    setLoading(true)
    try {
      const items = await projectApi.getStoryboards(projectId)
      setStoryboards(items)
      setActive((prev) => {
        if (!prev) return prev
        return items.find((item) => item.id === prev.id) || prev
      })
    } catch (error) {
      message.error('加载分镜列表失败')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadStoryboards()
  }, [projectId])

  useEffect(() => {
    const busy = storyboards.some(
      (item) => item.status === 'generating' || item.status === 'rendering'
    )
    if (!busy) return
    const timer = window.setInterval(() => {
      void loadStoryboards()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [storyboards, loadStoryboards])

  useEffect(() => {
    if (!active) {
      setEditedShots([])
      setPreviewUrl(null)
      return
    }
    setEditedShots(active.shots || [])
    if (active.status === 'completed') {
      setPreviewUrl(projectApi.getStoryboardVideoUrl(projectId, active.id))
    } else {
      setPreviewUrl(null)
    }
  }, [active, projectId])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const storyboard = await projectApi.generateStoryboardWithAI({
        project_id: projectId,
        custom_prompt: customPrompt.trim() || undefined,
        duration_ratio: durationRatio,
        scene_align: sceneAlign,
        subtitle_align: subtitleAlign,
        golden_opening: goldenOpening,
        aspect_ratio: aspectRatio,
        max_shots: maxShots,
      })
      setStoryboards((prev) => [storyboard, ...prev.filter((s) => s.id !== storyboard.id)])
      setActive(storyboard)
      message.success('AI 已生成分镜表，可编辑旁白后渲染')
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      message.error(detail || 'AI 分镜生成失败')
      console.error(error)
    } finally {
      setGenerating(false)
    }
  }

  const handleSaveShots = async () => {
    if (!active) return
    setSaving(true)
    try {
      const updated = await projectApi.updateStoryboard(active.id, { shots: editedShots })
      setActive(updated)
      setStoryboards((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
      message.success('分镜已保存')
    } catch (error) {
      message.error('保存失败')
      console.error(error)
    } finally {
      setSaving(false)
    }
  }

  const pollStoryboard = async (storyboardId: string): Promise<Storyboard> => {
    for (let i = 0; i < 120; i++) {
      const current = await projectApi.getStoryboard(storyboardId)
      if (current.status === 'completed' || current.status === 'failed') {
        return current
      }
      await new Promise((r) => window.setTimeout(r, 2500))
    }
    throw new Error('渲染超时')
  }

  const handleRender = async () => {
    if (!active) return
    setRendering(true)
    try {
      if (editedShots !== active.shots) {
        await projectApi.updateStoryboard(active.id, { shots: editedShots })
      }
      await projectApi.renderStoryboard(active.id)
      const updated = await pollStoryboard(active.id)
      setActive(updated)
      setStoryboards((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
      if (updated.status === 'completed') {
        setPreviewUrl(projectApi.getStoryboardVideoUrl(projectId, updated.id))
        message.success('无旁白成片渲染完成')
      } else {
        message.error(updated.error_message || '渲染失败')
      }
    } catch (error) {
      message.error('渲染失败')
      console.error(error)
    } finally {
      setRendering(false)
    }
  }

  const handleDownload = async () => {
    if (!active) return
    try {
      const blob = await projectApi.downloadStoryboard(projectId, active.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${active.name || 'storyboard'}.mp4`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      message.error('下载失败')
      console.error(error)
    }
  }

  const handleDelete = async (storyboardId: string) => {
    try {
      await projectApi.deleteStoryboard(storyboardId)
      setStoryboards((prev) => prev.filter((s) => s.id !== storyboardId))
      if (active?.id === storyboardId) setActive(null)
      message.success('已删除')
    } catch (error) {
      message.error('删除失败')
    }
  }

  const updateShotNarration = (shotId: string, narration: string) => {
    setEditedShots((prev) =>
      prev.map((shot) => (shot.id === shotId ? { ...shot, narration } : shot))
    )
  }

  const columns: ColumnsType<StoryboardShot> = useMemo(
    () => [
      {
        title: '序号',
        dataIndex: 'index',
        width: 64,
        render: (index: number) => <Text strong>{index}</Text>,
      },
      {
        title: '画面',
        dataIndex: 'id',
        width: 110,
        render: (id: string, record) => {
          if (!active) return null
          const url = projectApi.getStoryboardShotThumbnailUrl(projectId, active.id, id)
          return record.thumbnail_path ? (
            <img src={url} alt="" className="storyboard-shot-thumb" />
          ) : (
            <div className="storyboard-shot-thumb-empty">—</div>
          )
        },
      },
      {
        title: '旁白',
        dataIndex: 'narration',
        render: (text: string, record) => (
          <Input.TextArea
            value={text}
            autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(e) => updateShotNarration(record.id, e.target.value)}
          />
        ),
      },
      {
        title: '开始时间',
        dataIndex: 'start_time',
        width: 100,
        render: (v: number) => formatTime(v),
      },
      {
        title: '结束时间',
        dataIndex: 'end_time',
        width: 100,
        render: (v: number) => formatTime(v),
      },
    ],
    [active, projectId]
  )

  const listView = (
    <div className="storyboard-tab">
      <div className="storyboard-config-panel">
        <Title level={5} style={{ marginTop: 0 }}>
          AI 解说分镜
        </Title>
        <Text type="secondary">
          基于项目原片与字幕，AI 自动生成带旁白文案的分镜表（Phase 1：无旁白 TTS，先导出画面拼接成片）
        </Text>
        <div className="storyboard-config-row" style={{ marginTop: 16 }}>
          <div className="storyboard-config-item">
            <Text type="secondary">目标时长比例</Text>
            <InputNumber
              min={0.1}
              max={1}
              step={0.1}
              value={durationRatio}
              onChange={(v) => setDurationRatio(v ?? 0.5)}
              addonAfter={`${Math.round(durationRatio * 100)}%`}
              style={{ width: '100%', marginTop: 8 }}
            />
          </div>
          <div className="storyboard-config-item">
            <Text type="secondary">输出比例</Text>
            <Select
              value={aspectRatio}
              onChange={setAspectRatio}
              style={{ width: '100%', marginTop: 8 }}
              options={[
                { value: '9:16', label: '9:16 竖屏' },
                { value: '16:9', label: '16:9 横屏' },
              ]}
            />
          </div>
          <div className="storyboard-config-item">
            <Text type="secondary">最多镜头数</Text>
            <InputNumber
              min={4}
              max={30}
              value={maxShots}
              onChange={(v) => setMaxShots(v ?? 16)}
              style={{ width: '100%', marginTop: 8 }}
            />
          </div>
        </div>
        <TextArea
          rows={3}
          placeholder="默认要求，可填写：例如短剧解说、节奏快、开头要有悬念…"
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          style={{ marginTop: 12 }}
        />
        <Space wrap style={{ marginTop: 12 }}>
          <Switch checked={sceneAlign} onChange={setSceneAlign} />
          <Text>场景对齐</Text>
          <Switch checked={subtitleAlign} onChange={setSubtitleAlign} />
          <Text>字幕场景对齐</Text>
          <Switch checked={goldenOpening} onChange={setGoldenOpening} />
          <Text>黄金 5 秒开头</Text>
        </Space>
        <div style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={generating}
            onClick={handleGenerate}
          >
            生成分镜表
          </Button>
        </div>
      </div>

      {storyboards.length === 0 ? (
        <Empty description="还没有解说分镜，点击上方按钮开始" />
      ) : (
        <div className="storyboard-list-grid">
          {storyboards.map((item) => {
            const status = statusMap[item.status] || statusMap.draft
            return (
              <div
                key={item.id}
                className="storyboard-list-card"
                onClick={() => setActive(item)}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Text strong ellipsis>
                    {item.name}
                  </Text>
                  <Space size={6} wrap>
                    <Tag color={status.color}>{status.text}</Tag>
                    <Tag>{item.shot_count || item.shots?.length || 0} 镜</Tag>
                    {item.total_duration ? <Tag>{item.total_duration}s</Tag> : null}
                  </Space>
                  <Space>
                    <Button size="small" icon={<EditOutlined />}>
                      编辑
                    </Button>
                    <Popconfirm title="删除此分镜？" onConfirm={() => handleDelete(item.id)}>
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                </Space>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )

  const editorView = active && (
    <div className="storyboard-tab">
      <div className="storyboard-preview-bar">
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => setActive(null)}>
            返回列表
          </Button>
          <Title level={5} style={{ margin: 0 }}>
            {active.name}
          </Title>
          <Tag color={statusMap[active.status]?.color}>{statusMap[active.status]?.text}</Tag>
        </Space>
        <Space wrap>
          <Button icon={<RobotOutlined />} loading={saving} onClick={handleSaveShots}>
            保存旁白
          </Button>
          <Button
            type="primary"
            icon={<VideoCameraOutlined />}
            loading={rendering}
            disabled={editedShots.length < 2}
            onClick={handleRender}
          >
            无旁白导出
          </Button>
          {active.status === 'completed' && (
            <Button icon={<DownloadOutlined />} onClick={handleDownload}>
              下载成片
            </Button>
          )}
        </Space>
      </div>

      {active.error_message && active.status === 'failed' && (
        <Text type="danger">{active.error_message}</Text>
      )}

      {previewUrl && (
        <video
          src={previewUrl}
          controls
          style={{ width: '100%', maxHeight: 360, borderRadius: 12, background: '#000' }}
        />
      )}

      <div className="storyboard-table-wrap">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={editedShots}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
          size="middle"
        />
      </div>
    </div>
  )

  const body = (
    <Spin spinning={generating || rendering || loading}>
      {active ? editorView : listView}
    </Spin>
  )

  if (embedded) {
    return <div className="storyboard-tab-root storyboard-tab-embedded">{body}</div>
  }

  return (
    <Card loading={loading} className="storyboard-tab-root">
      <Spin spinning={generating || rendering}>{active ? editorView : listView}</Spin>
    </Card>
  )
}

export default StoryboardTab
