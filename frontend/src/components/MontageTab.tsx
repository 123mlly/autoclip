import React, { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Typography,
  message,
  Select,
  InputNumber,
  Switch,
} from 'antd'
import {
  PlusOutlined,
  ScissorOutlined,
  EditOutlined,
  DeleteOutlined,
  ClockCircleOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import { Clip } from '../store/useProjectStore'
import { Montage, projectApi } from '../services/api'
import MontageEditorModal from './MontageEditorModal'
import './MontageTab.css'

const { Title, Text } = Typography
const { TextArea } = Input

interface MontageTabProps {
  projectId: string
  clips: Clip[]
}

const statusLabel: Record<Montage['status'], { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  rendering: { color: 'processing', text: '渲染中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

const MontageTab: React.FC<MontageTabProps> = ({ projectId, clips }) => {
  const [montages, setMontages] = useState<Montage[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createName, setCreateName] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showAiModal, setShowAiModal] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiAspectRatio, setAiAspectRatio] = useState<'9:16' | '16:9'>('9:16')
  const [aiTargetDuration, setAiTargetDuration] = useState(60)
  const [aiIncludeOtherProjects, setAiIncludeOtherProjects] = useState(false)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [editingMontage, setEditingMontage] = useState<Montage | null>(null)
  const [showEditor, setShowEditor] = useState(false)

  const loadMontages = useCallback(async () => {
    setLoading(true)
    try {
      const items = await projectApi.getMontages(projectId)
      setMontages(items)
    } catch (error) {
      message.error('加载混剪列表失败')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadMontages()
  }, [loadMontages])

  useEffect(() => {
    const hasRendering = montages.some((item) => item.status === 'rendering')
    if (!hasRendering) return
    const timer = window.setInterval(() => {
      void loadMontages()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [montages, loadMontages])

  const handleCreate = async () => {
    const name = createName.trim()
    if (!name) {
      message.warning('请输入混剪名称')
      return
    }
    setCreating(true)
    try {
      const montage = await projectApi.createMontage(projectId, name)
      setMontages((prev) => [montage, ...prev])
      setShowCreateModal(false)
      setCreateName('')
      setEditingMontage(montage)
      setShowEditor(true)
      message.success('混剪已创建')
    } catch (error) {
      message.error('创建混剪失败')
      console.error(error)
    } finally {
      setCreating(false)
    }
  }

  const handleAiGenerate = async () => {
    const prompt = aiPrompt.trim()
    if (!prompt) {
      message.warning('请描述你想要的混剪效果')
      return
    }
    if (clips.length < 2) {
      message.warning('当前项目至少需要 2 个切片才能 AI 混剪')
      return
    }
    setAiGenerating(true)
    try {
      const montage = await projectApi.generateMontageWithAI({
        project_id: projectId,
        prompt,
        aspect_ratio: aiAspectRatio,
        target_duration: aiTargetDuration,
        include_other_projects: aiIncludeOtherProjects,
      })
      setMontages((prev) => [montage, ...prev])
      setShowAiModal(false)
      setAiPrompt('')
      setEditingMontage(montage)
      setShowEditor(true)
      message.success('AI 已生成混剪方案，可在编辑器中微调后渲染')
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      message.error(detail || 'AI 混剪生成失败')
      console.error(error)
    } finally {
      setAiGenerating(false)
    }
  }

  const handleDelete = async (montageId: string) => {
    try {
      await projectApi.deleteMontage(montageId)
      setMontages((prev) => prev.filter((item) => item.id !== montageId))
      message.success('混剪已删除')
    } catch (error) {
      message.error('删除失败')
      console.error(error)
    }
  }

  const handleOpenEditor = (montage: Montage) => {
    setEditingMontage(montage)
    setShowEditor(true)
  }

  const handleMontageUpdated = (montage: Montage) => {
    setMontages((prev) => prev.map((item) => (item.id === montage.id ? montage : item)))
    setEditingMontage(montage)
  }

  return (
    <div className="montage-tab">
      <Card loading={loading}>
        <div className="montage-header">
          <div>
            <Title level={4} style={{ margin: 0 }}>
              混剪
            </Title>
            <Text type="secondary">从切片中挑选片段，按顺序裁剪并合成新视频；也支持 AI 一键编排</Text>
          </div>
          <Space>
            <Button icon={<RobotOutlined />} onClick={() => setShowAiModal(true)}>
              AI 混剪
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowCreateModal(true)}>
              新建混剪
            </Button>
          </Space>
        </div>

        {montages.length === 0 ? (
          <div style={{ padding: '48px 0' }}>
            <Empty
              image={<ScissorOutlined style={{ fontSize: 48, color: '#b8c4d1' }} />}
              description={
                <div>
                  <Text type="secondary">还没有混剪项目</Text>
                  <br />
                  <Button
                    type="link"
                    onClick={() => setShowAiModal(true)}
                    style={{ padding: 0, marginTop: 8, marginRight: 12 }}
                  >
                    AI 一键混剪
                  </Button>
                  <Button
                    type="link"
                    onClick={() => setShowCreateModal(true)}
                    style={{ padding: 0, marginTop: 8 }}
                  >
                    手动创建混剪
                  </Button>
                </div>
              }
            />
          </div>
        ) : (
          <div className="montage-grid" style={{ marginTop: 20 }}>
            {montages.map((montage) => {
              const status = statusLabel[montage.status] || statusLabel.draft
              return (
                <div key={montage.id} className="montage-card">
                  <div
                    className="montage-card-cover"
                    onClick={() => handleOpenEditor(montage)}
                  >
                    {montage.status === 'completed' ? (
                      <ScissorOutlined style={{ fontSize: 36, color: '#0e7c66' }} />
                    ) : (
                      <ScissorOutlined style={{ fontSize: 36, color: '#9aa5b1' }} />
                    )}
                  </div>
                  <div className="montage-card-body">
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: 8,
                        alignItems: 'flex-start',
                      }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <Text strong ellipsis style={{ display: 'block' }}>
                          {montage.name}
                        </Text>
                        <Space size={6} wrap style={{ marginTop: 6 }}>
                          <Tag color={status.color}>{status.text}</Tag>
                          <Tag icon={<ClockCircleOutlined />}>
                            {montage.segment_count || montage.timeline?.segments?.length || 0} 段
                          </Tag>
                          {montage.total_duration ? (
                            <Tag>{montage.total_duration}s</Tag>
                          ) : null}
                          <Tag>
                            {(montage.timeline?.output?.aspect_ratio || '9:16') === '16:9'
                              ? '16:9 横屏'
                              : '9:16 竖屏'}
                          </Tag>
                        </Space>
                      </div>
                      <Space size={4}>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => handleOpenEditor(montage)}
                        />
                        <Popconfirm
                          title="删除此混剪？"
                          onConfirm={() => handleDelete(montage.id)}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      <Modal
        title="新建混剪"
        open={showCreateModal}
        onCancel={() => {
          setShowCreateModal(false)
          setCreateName('')
        }}
        onOk={handleCreate}
        confirmLoading={creating}
        okText="创建"
      >
        <Input
          placeholder="例如：越南柬埔寨旅行精华"
          value={createName}
          onChange={(e) => setCreateName(e.target.value)}
          onPressEnter={handleCreate}
        />
      </Modal>

      <Modal
        title="AI 一键混剪"
        open={showAiModal}
        onCancel={() => {
          if (aiGenerating) return
          setShowAiModal(false)
          setAiPrompt('')
        }}
        onOk={handleAiGenerate}
        confirmLoading={aiGenerating}
        okText="生成方案"
        width={560}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <Text type="secondary">描述你想要的混剪效果，AI 会自动选片、排序并设置转场</Text>
            <TextArea
              rows={4}
              placeholder="例如：把旅行相关的精彩片段剪成 60 秒抖音竖屏精华，节奏快一点，开头要抓人"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div>
              <Text type="secondary">输出比例</Text>
              <Select
                value={aiAspectRatio}
                onChange={setAiAspectRatio}
                style={{ width: 140, display: 'block', marginTop: 8 }}
                options={[
                  { value: '9:16', label: '9:16 竖屏' },
                  { value: '16:9', label: '16:9 横屏' },
                ]}
              />
            </div>
            <div>
              <Text type="secondary">目标时长（秒）</Text>
              <InputNumber
                min={15}
                max={600}
                value={aiTargetDuration}
                onChange={(value) => setAiTargetDuration(value ?? 60)}
                style={{ width: 140, display: 'block', marginTop: 8 }}
              />
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Switch
              checked={aiIncludeOtherProjects}
              onChange={setAiIncludeOtherProjects}
            />
            <Text>允许从其他已完成项目中选片</Text>
          </div>
        </Space>
      </Modal>

      <MontageEditorModal
        visible={showEditor}
        montage={editingMontage}
        clips={clips}
        projectId={projectId}
        onClose={() => {
          setShowEditor(false)
          setEditingMontage(null)
        }}
        onUpdated={handleMontageUpdated}
      />
    </div>
  )
}

export default MontageTab
