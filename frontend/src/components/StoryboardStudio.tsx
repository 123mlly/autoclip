import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tag,
  Typography,
  message,
  Badge,
  Divider,
  Popconfirm,
  Spin,
  Drawer,
  List,
  Tooltip,
} from 'antd'
import {
  SendOutlined,
  EditOutlined,
  DownloadOutlined,
  VideoCameraOutlined,
  PlusOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
  HistoryOutlined,
  SearchOutlined,
  RightOutlined,
  SoundOutlined,
  DownOutlined,
  GlobalOutlined,
  SwapOutlined,
  QuestionCircleOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import type { ColumnsType } from 'antd/es/table'
import {
  Storyboard,
  StoryboardProjectSummary,
  StoryboardShot,
  StoryboardVideoSource,
  projectApi,
  settingsApi,
} from '../services/api'
import UploadModal from './UploadModal'
import './StoryboardStudio.css'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const { Text } = Typography
const { TextArea } = Input

const REQUIREMENT_PRESETS = [
  { value: 'default', label: '默认要求' },
  { value: 'short_drama', label: '短剧解说' },
  { value: 'fast', label: '快节奏精华' },
  { value: 'suspense', label: '悬念反转' },
]

const NARRATION_STYLE_PRESETS = [
  { value: 'colloquial', label: '口语化解说' },
  { value: 'punchy', label: '快节奏短句' },
  { value: 'suspense', label: '悬念抓人' },
  { value: 'documentary', label: '客观叙述' },
  { value: 'minimal', label: '轻量补充' },
]

const LEGACY_VOICE_STYLE_MAP: Record<string, string> = {
  mandarin: 'colloquial',
  original: 'minimal',
}

const NARRATION_STYLE_PROMPTS: Record<string, string> = {
  colloquial: '旁白用口语化写法，像朋友聊天，适合短视频朗读，避免书面语。',
  punchy: '旁白用快节奏短句，一句一个信息点，不拖沓，字数控制在上限内。',
  suspense: '旁白以悬念和反转抓人，多用提问、转折和留白，激发观众继续看。',
  documentary: '旁白用客观第三人称叙述，语气平静、清晰，不过度情绪化。',
  minimal: '旁白只做画面补充，不重复原声对白，每镜字数宜少。',
}

function normalizeVoiceStyle(value?: string): string {
  const raw = value || 'colloquial'
  const mapped = LEGACY_VOICE_STYLE_MAP[raw] || raw
  return NARRATION_STYLE_PROMPTS[mapped] ? mapped : 'colloquial'
}

const GOLDEN_PRESETS = [
  { value: 'viral_5s', label: '黄金5秒爆款开头' },
  { value: 'normal', label: '常规开头' },
]

const TRANSLATE_LANG_OPTIONS = [
  { value: 'en', label: '英文' },
  { value: 'ja', label: '日文' },
  { value: 'ko', label: '韩文' },
]

type ExportPhase = 'idle' | 'save' | 'render' | 'download' | 'done' | 'error'

const EXPORT_PHASE_LABEL: Record<ExportPhase, string> = {
  idle: '',
  save: '正在保存分镜修改…',
  render: '正在合成视频，请稍候…',
  download: '正在准备下载…',
  done: '导出完成',
  error: '导出失败',
}

const STATUS_MAP: Record<
  Storyboard['status'],
  { color: string; text: string }
> = {
  draft: { color: 'default', text: '草稿' },
  generating: { color: 'processing', text: '生成中' },
  ready: { color: 'success', text: '就绪' },
  rendering: { color: 'processing', text: '渲染中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

const SESSION_KEY = 'autoclip-storyboard-studio'

interface StudioSession {
  projectId?: string
  projectName?: string
  storyboardId?: string
}

const formatTime = (seconds: number): string => Number(seconds).toFixed(2)

const formatFileSize = (bytes: number): string => {
  if (!bytes) return '0 B'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

const getApiErrorDetail = (error: unknown): string | undefined => {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    const detail = response?.data?.detail
    return typeof detail === 'string' ? detail : undefined
  }
  return undefined
}

const isNotFoundError = (error: unknown): boolean => {
  if (error && typeof error === 'object' && 'response' in error) {
    return (error as { response?: { status?: number } }).response?.status === 404
  }
  return false
}

interface ModelOption {
  name: string
  display_name?: string
}

const buildModelOptions = (
  allModels: Record<string, ModelOption[]>,
  providerKey: string,
  currentModel: string
): { value: string; label: string }[] => {
  const providerList = allModels?.[providerKey] || []
  const opts = providerList.map((model) => {
    const name = model.name
    const display = model.display_name?.trim()
    const label =
      display && display !== name ? `${display} (${name})` : name
    return {
      value: name,
      label: name === currentModel ? `${label}（当前）` : label,
    }
  })

  if (currentModel && !opts.some((o) => o.value === currentModel)) {
    opts.unshift({ value: currentModel, label: `${currentModel}（当前）` })
  }

  if (opts.length === 0 && currentModel) {
    return [{ value: currentModel, label: `${currentModel}（当前）` }]
  }

  return opts
}

const applyConfigFromStoryboard = (
  sb: Storyboard,
  setters: {
    setDurationRatio: (v: number) => void
    setMaxShots: (v: number) => void
    setSceneAlign: (v: boolean) => void
    setSubtitleAlign: (v: boolean) => void
    setGoldenOpening: (v: boolean) => void
    setAspectRatio: (v: '9:16' | '16:9') => void
    setCustomPrompt: (v: string) => void
    setSelectedModel: (v: string) => void
    setVoiceStyle: (v: string) => void
    setNarrationMaxChars: (v: number) => void
  }
) => {
  const c = sb.config || {}
  if (c.duration_ratio != null) setters.setDurationRatio(c.duration_ratio)
  if (c.max_shots != null) setters.setMaxShots(c.max_shots)
  if (c.narration_max_chars != null) setters.setNarrationMaxChars(c.narration_max_chars)
  if (c.scene_align != null) setters.setSceneAlign(c.scene_align)
  if (c.subtitle_align != null) setters.setSubtitleAlign(c.subtitle_align)
  if (c.golden_opening != null) setters.setGoldenOpening(c.golden_opening)
  if (c.aspect_ratio === '9:16' || c.aspect_ratio === '16:9') {
    setters.setAspectRatio(c.aspect_ratio)
  }
  if (typeof c.user_custom_prompt === 'string') {
    setters.setCustomPrompt(c.user_custom_prompt)
  } else {
    setters.setCustomPrompt('')
  }
  if (c.model_name) setters.setSelectedModel(c.model_name)
  if (c.voice_style) setters.setVoiceStyle(normalizeVoiceStyle(c.voice_style))
}

const StoryboardStudio: React.FC = () => {
  const [subTab, setSubTab] = useState<'upload' | 'storyboard'>('upload')
  const [projectId, setProjectId] = useState<string>()
  const [projectName, setProjectName] = useState(
    () => `新建项目 ${new Date().toLocaleString('zh-CN', { hour12: false })}`
  )
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null)
  const [editedShots, setEditedShots] = useState<StoryboardShot[]>([])
  const [generating, setGenerating] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [uploadingVideos, setUploadingVideos] = useState(false)
  const [videoSources, setVideoSources] = useState<StoryboardVideoSource[]>([])

  const [srtFile, setSrtFile] = useState<File | null>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)
  const srtInputRef = useRef<HTMLInputElement>(null)
  const studioVersionRef = useRef(0)

  const resetStudioState = useCallback(() => {
    studioVersionRef.current += 1
    sessionStorage.removeItem(SESSION_KEY)
    setProjectId(undefined)
    setStoryboard(null)
    setEditedShots([])
    setVideoSources([])
    setSrtFile(null)
    setSubTab('upload')
    setHistoryDrawerOpen(false)
    setHistorySearch('')
    setGenerating(false)
    setRendering(false)
    setExportModalOpen(false)
    setExportPhase('idle')
    setExportError('')
    setUploadModalOpen(false)
    setUploadClipId('')
    setUploadClipTitle('')
    setPreparingUpload(false)
    setProjectName(`新建项目 ${new Date().toLocaleString('zh-CN', { hour12: false })}`)
    if (videoInputRef.current) videoInputRef.current.value = ''
    if (srtInputRef.current) srtInputRef.current.value = ''
  }, [])

  const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [voiceStyle, setVoiceStyle] = useState('colloquial')
  const [requirementPreset, setRequirementPreset] = useState('default')
  const [durationRatio, setDurationRatio] = useState(0.5)
  const [maxShots, setMaxShots] = useState(10)
  const [narrationMaxChars, setNarrationMaxChars] = useState(10)
  const [goldenOpening, setGoldenOpening] = useState(true)
  const [aspectRatio, setAspectRatio] = useState<'9:16' | '16:9'>('9:16')
  const [sceneAlign, setSceneAlign] = useState(true)
  const [subtitleAlign, setSubtitleAlign] = useState(true)
  const [customPrompt, setCustomPrompt] = useState('')

  const [replaceModalOpen, setReplaceModalOpen] = useState(false)
  const [replaceFind, setReplaceFind] = useState('')
  const [replaceWith, setReplaceWith] = useState('')
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const [exportPhase, setExportPhase] = useState<ExportPhase>('idle')
  const [exportError, setExportError] = useState('')
  const [exportWithNarration, setExportWithNarration] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadClipId, setUploadClipId] = useState('')
  const [uploadClipTitle, setUploadClipTitle] = useState('')
  const [preparingUpload, setPreparingUpload] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [saving, setSaving] = useState(false)
  const [historyProjects, setHistoryProjects] = useState<StoryboardProjectSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)
  const [historySearch, setHistorySearch] = useState('')

  const hasShots = editedShots.length > 0
  const hasUploadedVideos = videoSources.length > 0
  const currentStep = subTab === 'upload' ? 0 : 1

  const hasUnsavedChanges = useMemo(() => {
    if (!storyboard) return false
    return JSON.stringify(editedShots) !== JSON.stringify(storyboard.shots || [])
  }, [editedShots, storyboard])

  const hasNarrationText = useMemo(
    () => editedShots.some((shot) => (shot.narration || '').trim()),
    [editedShots]
  )

  const filteredHistoryProjects = useMemo(() => {
    const keyword = historySearch.trim().toLowerCase()
    if (!keyword) return historyProjects
    return historyProjects.filter((item) => item.name.toLowerCase().includes(keyword))
  }, [historyProjects, historySearch])

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY)
      if (!raw) return
      const session = JSON.parse(raw) as StudioSession
      if (session.projectId) setProjectId(session.projectId)
      if (session.projectName) setProjectName(session.projectName)
    } catch {
      /* ignore */
    }
  }, [])

  const loadVideoSources = useCallback(async (pid: string) => {
    const version = studioVersionRef.current
    try {
      const result = await projectApi.getStoryboardVideoSources(pid)
      if (version !== studioVersionRef.current) return
      setVideoSources(result.items || [])
    } catch (error) {
      if (version !== studioVersionRef.current) return
      setVideoSources([])
    }
  }, [])

  useEffect(() => {
    if (!projectId) {
      setVideoSources([])
      return
    }
    void loadVideoSources(projectId)
  }, [projectId, loadVideoSources])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const result = await projectApi.getStoryboardProjects({ page: 1, size: 50 })
      setHistoryProjects(result.items || [])
    } catch {
      setHistoryProjects([])
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  useEffect(() => {
    if (historyLoading || !projectId) return
    if (historyProjects.some((item) => item.project_id === projectId)) return
    resetStudioState()
    message.warning('当前项目已不存在，请新建或从混剪项目中选择')
  }, [historyLoading, historyProjects, projectId, resetStudioState])

  const loadExistingStoryboard = useCallback(async (pid: string, preferredId?: string) => {
    const version = studioVersionRef.current
    try {
      if (preferredId) {
        const sb = await projectApi.getStoryboard(preferredId)
        if (version !== studioVersionRef.current) return
        if (sb.project_id === pid) {
          setStoryboard(sb)
          setEditedShots(sb.shots || [])
          applyConfigFromStoryboard(sb, {
            setDurationRatio,
            setMaxShots,
            setSceneAlign,
            setSubtitleAlign,
            setGoldenOpening,
            setAspectRatio,
            setCustomPrompt,
            setSelectedModel,
            setVoiceStyle,
            setNarrationMaxChars,
          })
          if (sb.shots?.length) setSubTab('storyboard')
          return
        }
      }
      const items = await projectApi.getStoryboards(pid)
      if (version !== studioVersionRef.current) return
      if (items.length > 0) {
        const latest = items[0]
        setStoryboard(latest)
        setEditedShots(latest.shots || [])
        applyConfigFromStoryboard(latest, {
          setDurationRatio,
          setMaxShots,
          setSceneAlign,
          setSubtitleAlign,
          setGoldenOpening,
          setAspectRatio,
          setCustomPrompt,
          setSelectedModel,
          setVoiceStyle,
          setNarrationMaxChars,
        })
        if (latest.shots?.length) setSubTab('storyboard')
      } else {
        setStoryboard(null)
        setEditedShots([])
        setSubTab('upload')
      }
    } catch {
      if (version !== studioVersionRef.current) return
      setStoryboard(null)
      setEditedShots([])
      setSubTab('upload')
    }
  }, [])

  useEffect(() => {
    if (!projectId || storyboard) return
    let preferredId: string | undefined
    try {
      const raw = sessionStorage.getItem(SESSION_KEY)
      preferredId = raw ? (JSON.parse(raw) as StudioSession).storyboardId : undefined
    } catch {
      /* ignore */
    }
    void loadExistingStoryboard(projectId, preferredId)
  }, [projectId, storyboard, loadExistingStoryboard])

  useEffect(() => {
    const session: StudioSession = {
      projectId,
      projectName,
      storyboardId: storyboard?.id,
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
  }, [projectId, projectName, storyboard?.id])

  useEffect(() => {
    void (async () => {
      try {
        const [settings, provider, allModels] = await Promise.all([
          settingsApi.getSettings(),
          settingsApi.getCurrentProvider(),
          settingsApi.getAvailableModels(),
        ])

        const providerKey = provider?.provider || settings?.llm_provider || 'dashscope'
        const currentModel = settings?.model_name || provider?.model || ''
        const opts = buildModelOptions(allModels || {}, providerKey, currentModel)

        setModelOptions(opts)
        setSelectedModel((prev) => prev || currentModel || opts[0]?.value || '')
      } catch {
        try {
          const provider = await settingsApi.getCurrentProvider()
          const currentModel = provider?.model || ''
          if (currentModel) {
            setModelOptions([{ value: currentModel, label: `${currentModel}（当前）` }])
            setSelectedModel((prev) => prev || currentModel)
          }
        } catch {
          setModelOptions([])
        }
      }
    })()
  }, [])

  useEffect(() => {
    const busy =
      storyboard?.status === 'generating' ||
      storyboard?.status === 'rendering' ||
      generating ||
      rendering
    if (!busy || !storyboard?.id) return
    const storyboardId = storyboard.id
    const version = studioVersionRef.current
    const timer = window.setInterval(async () => {
      if (version !== studioVersionRef.current) return
      try {
        const current = await projectApi.getStoryboard(storyboardId)
        if (version !== studioVersionRef.current) return
        setStoryboard(current)
        setEditedShots(current.shots || [])
      } catch {
        if (version !== studioVersionRef.current) return
        setStoryboard(null)
        setEditedShots([])
        setSubTab('upload')
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [storyboard?.id, storyboard?.status, generating, rendering])

  const goToStep = (step: 0 | 1) => {
    if (step === 1 && !hasShots) {
      message.info('请先在第一步上传素材并生成分镜表')
      return
    }
    setSubTab(step === 0 ? 'upload' : 'storyboard')
  }

  const uploadVideoFiles = async (files: FileList | File[]) => {
    const picked = Array.from(files).filter(
      (f) => f.type.startsWith('video/') || f.name.toLowerCase().endsWith('.mp4')
    )
    if (picked.length === 0) {
      message.warning('请选择 MP4 视频文件')
      return
    }

    const createNewProjectWithVideos = async () => {
      const formData = new FormData()
      picked.forEach((file) => formData.append('video_files', file))
      if (srtFile) formData.append('srt_file', srtFile)
      formData.append('project_name', projectName.trim() || 'AI 混剪项目')
      const res = await projectApi.setupStoryboardProject(formData)
      setProjectId(res.project_id)
      setVideoSources(res.items || [])
      return res
    }

    setUploadingVideos(true)
    try {
      if (!projectId) {
        await createNewProjectWithVideos()
        message.success(`已上传 ${picked.length} 个视频`)
      } else {
        try {
          const res = await projectApi.appendStoryboardVideos(projectId, picked)
          setVideoSources(res.items || [])
          message.success(`已追加 ${picked.length} 个视频，共 ${res.source_count} 个`)
        } catch (error) {
          if (!isNotFoundError(error)) throw error
          setProjectId(undefined)
          setVideoSources([])
          await createNewProjectWithVideos()
          message.warning(`原项目已失效，已创建新项目并上传 ${picked.length} 个视频`)
        }
      }
      void loadHistory()
      if (videoInputRef.current) videoInputRef.current.value = ''
    } catch (error) {
      message.error(getApiErrorDetail(error) || '视频上传失败')
    } finally {
      setUploadingVideos(false)
    }
  }

  const handleDeleteVideoSource = async (sourceId: string) => {
    if (!projectId) return
    try {
      const res = await projectApi.deleteStoryboardVideoSource(projectId, sourceId)
      setVideoSources(res.items || [])
      message.success('已删除上传记录')
    } catch {
      message.error('删除失败')
    }
  }

  const buildPrompt = (): string => {
    const presetMap: Record<string, string> = {
      default: '',
      short_drama: '短剧混剪风格，突出冲突与反转。',
      fast: '节奏快，信息密度高，不要拖沓。',
      suspense: '开头制造悬念，层层推进。',
    }
    const parts = [presetMap[requirementPreset] || '', customPrompt.trim()].filter(Boolean)
    parts.push(NARRATION_STYLE_PROMPTS[normalizeVoiceStyle(voiceStyle)])
    return parts.join(' ')
  }

  const ensureProject = async (): Promise<string> => {
    if (projectId) {
      if (srtFile) {
        await projectApi.uploadStoryboardSubtitle(projectId, srtFile)
      }
      return projectId
    }
    throw new Error('请先上传视频')
  }

  const handleGenerate = async () => {
    if (!projectId && !hasUploadedVideos) {
      message.warning('请先上传 MP4 视频')
      return
    }
    setGenerating(true)
    try {
      const pid = await ensureProject()
      if (!srtFile && (sceneAlign || subtitleAlign)) {
        message.loading({
          content: '未检测到字幕，正在自动识别语音（可能需要几分钟）…',
          key: 'storyboard-asr',
          duration: 0,
        })
      }
      const result = await projectApi.generateStoryboardWithAI({
        project_id: pid,
        name: projectName,
        custom_prompt: buildPrompt(),
        user_custom_prompt: customPrompt.trim() || undefined,
        duration_ratio: durationRatio,
        scene_align: sceneAlign,
        subtitle_align: subtitleAlign,
        golden_opening: goldenOpening,
        aspect_ratio: aspectRatio,
        max_shots: maxShots,
        narration_max_chars: narrationMaxChars,
        model_name: selectedModel || undefined,
        voice_style: voiceStyle,
      })
      setStoryboard(result)
      setEditedShots(result.shots || [])
      setSubTab('storyboard')
      message.destroy('storyboard-asr')
      message.success('分镜表已生成，可在「分镜表」中编辑')
      void loadHistory()
    } catch (error: unknown) {
      message.destroy('storyboard-asr')
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      message.error(detail || '生成分镜失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleSaveShots = async () => {
    if (!storyboard) return
    setSaving(true)
    try {
      const updated = await projectApi.updateStoryboard(storyboard.id, {
        shots: editedShots,
        config: { ...storyboard.config, narration_max_chars: narrationMaxChars },
      })
      setStoryboard(updated)
      setEditedShots(updated.shots || [])
      message.success('分镜修改已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const downloadStoryboardVideo = useCallback(
    async (sb: Storyboard, withNarration = false) => {
      if (!projectId) return
      const blob = await projectApi.downloadStoryboard(projectId, sb.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sb.name || 'storyboard'}${withNarration ? '_旁白' : ''}.mp4`
      a.click()
      URL.revokeObjectURL(url)
    },
    [projectId]
  )

  const handleExportVideo = async (withNarration = false) => {
    if (!storyboard || !projectId) {
      message.warning('请先完成分镜表生成')
      return
    }
    if (editedShots.length === 0) {
      message.warning('分镜表为空，无法导出')
      return
    }
    if (withNarration && !editedShots.some((shot) => (shot.narration || '').trim())) {
      message.warning('分镜表中还没有旁白，请先生成或手动填写')
      return
    }

    setExportWithNarration(withNarration)
    setRendering(true)
    setExportModalOpen(true)
    setExportPhase('save')
    setExportError('')

    try {
      await projectApi.updateStoryboard(storyboard.id, {
        shots: editedShots,
        config: { ...storyboard.config, narration_max_chars: narrationMaxChars },
      })
      setExportPhase('render')
      let current = await projectApi.renderStoryboard(storyboard.id, true, withNarration)
      if (current.status === 'rendering') {
        for (let i = 0; i < 60; i++) {
          current = await projectApi.getStoryboard(storyboard.id)
          if (current.status === 'completed' || current.status === 'failed') break
          await new Promise((r) => window.setTimeout(r, 2000))
        }
      }
      setStoryboard(current)
      if (current.status === 'completed') {
        setExportPhase('download')
        await downloadStoryboardVideo(current, withNarration)
        setExportPhase('done')
        message.success(
          withNarration ? '带旁白字幕的视频已导出并开始下载' : '纯画面视频已导出并开始下载'
        )
        window.setTimeout(() => {
          setExportModalOpen(false)
          setExportPhase('idle')
        }, 1200)
      } else {
        setExportPhase('error')
        setExportError(current.error_message || '渲染失败，请重试')
      }
    } catch (err: unknown) {
      setExportPhase('error')
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setExportError(typeof detail === 'string' ? detail : '导出失败，请检查网络或稍后重试')
    } finally {
      setRendering(false)
    }
  }

  const handleOpenUpload = async () => {
    if (!storyboard || !projectId) {
      message.warning('缺少项目信息，无法投稿')
      return
    }
    if (storyboard.status !== 'completed') {
      message.warning('请先导出视频后再投稿')
      return
    }
    setPreparingUpload(true)
    try {
      const result = await projectApi.prepareStoryboardUpload(storyboard.id)
      setUploadClipId(result.clip_id)
      setUploadClipTitle(result.title || storyboard.name || projectName)
      setExportModalOpen(false)
      setUploadModalOpen(true)
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      message.error(typeof detail === 'string' ? detail : '准备投稿失败')
    } finally {
      setPreparingUpload(false)
    }
  }

  const exportProgressPercent = useMemo(() => {
    switch (exportPhase) {
      case 'save':
        return 20
      case 'render':
        return 55
      case 'download':
        return 85
      case 'done':
        return 100
      case 'error':
        return 100
      default:
        return 0
    }
  }, [exportPhase])

  const handleExtractNarrations = async () => {
    if (!storyboard) return
    try {
      const updated = await projectApi.extractStoryboardNarrations(storyboard.id)
      setStoryboard(updated)
      setEditedShots(updated.shots || [])
      message.success('已用原片字幕填充旁白')
    } catch {
      message.error('填充失败，请在上传步骤导入 SRT 字幕')
    }
  }

  const handleBatchTranslate = async (lang = 'en') => {
    if (!storyboard) return
    try {
      const updated = await projectApi.batchTranslateStoryboard(storyboard.id, lang)
      setStoryboard(updated)
      setEditedShots(updated.shots || [])
      message.success('旁白翻译完成')
    } catch {
      message.error('翻译失败，请稍后重试')
    }
  }

  const handleBatchReplace = async () => {
    if (!storyboard || !replaceFind.trim()) return
    try {
      const updated = await projectApi.batchReplaceStoryboardText(
        storyboard.id,
        replaceFind,
        replaceWith
      )
      setStoryboard(updated)
      setEditedShots(updated.shots || [])
      setReplaceModalOpen(false)
      setReplaceFind('')
      setReplaceWith('')
      message.success('旁白替换完成')
    } catch {
      message.error('替换失败，请稍后重试')
    }
  }

  const copyToolsMenu = {
    items: [
      {
        key: 'extract',
        icon: <FileTextOutlined />,
        label: '从原片字幕填充旁白',
        onClick: () => void handleExtractNarrations(),
      },
      { type: 'divider' as const },
      {
        key: 'translate',
        icon: <GlobalOutlined />,
        label: '翻译旁白',
        children: TRANSLATE_LANG_OPTIONS.map((opt) => ({
          key: `translate-${opt.value}`,
          label: opt.label,
          onClick: () => void handleBatchTranslate(opt.value),
        })),
      },
      { type: 'divider' as const },
      {
        key: 'replace',
        icon: <SwapOutlined />,
        label: '查找并替换…',
        onClick: () => setReplaceModalOpen(true),
      },
    ],
  }

  const exportMenu = {
    items: [
      {
        key: 'narration',
        icon: <SoundOutlined />,
        label: hasNarrationText ? '带旁白字幕' : '带旁白字幕（暂无旁白）',
        disabled: !hasNarrationText,
      },
      {
        key: 'silent',
        icon: <VideoCameraOutlined />,
        label: '纯画面（无字幕）',
      },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'narration') void handleExportVideo(true)
      if (key === 'silent') void handleExportVideo(false)
    },
  }

  const handleNewProject = () => {
    resetStudioState()
  }

  const openHistoryProject = async (item: StoryboardProjectSummary) => {
    studioVersionRef.current += 1
    const version = studioVersionRef.current
    setProjectId(item.project_id)
    setProjectName(item.name)
    setSrtFile(null)
    setStoryboard(null)
    setEditedShots([])
    setHistoryDrawerOpen(false)
    setHistorySearch('')
    await loadVideoSources(item.project_id)
    if (version !== studioVersionRef.current) return
    await loadExistingStoryboard(item.project_id, item.storyboard_id || undefined)
    if (version !== studioVersionRef.current) return
    if (!item.storyboard_id || item.shot_count === 0) {
      setSubTab('upload')
    }
  }

  const handleDeleteHistoryProject = async (item: StoryboardProjectSummary) => {
    const isActiveProject =
      projectId === item.project_id || storyboard?.project_id === item.project_id
    if (isActiveProject) {
      resetStudioState()
    }
    try {
      await projectApi.deleteProject(item.project_id)
      message.success('已删除混剪项目')
      await loadHistory()
    } catch {
      message.error('删除失败')
      if (isActiveProject) {
        await loadHistory()
      }
    }
  }

  const updateShotNarration = (shotId: string, narration: string) => {
    setEditedShots((prev) =>
      prev.map((shot) => (shot.id === shotId ? { ...shot, narration } : shot))
    )
  }

  const columns: ColumnsType<StoryboardShot> = useMemo(
    () => [
      { title: '序号', dataIndex: 'index', width: 64 },
      {
        title: '画面',
        dataIndex: 'id',
        width: 110,
        render: (id: string, record) => {
          if (!storyboard || !projectId) return null
          if (record.thumbnail_path) {
            return (
              <img
                src={projectApi.getStoryboardShotThumbnailUrl(projectId, storyboard.id, id)}
                alt=""
                className="storyboard-shot-thumb"
              />
            )
          }
          return <div className="storyboard-shot-thumb-empty">—</div>
        },
      },
      {
        title: '旁白',
        dataIndex: 'narration',
        render: (text: string, record) => (
          <TextArea
            value={text}
            placeholder={`输入旁白，最多 ${narrationMaxChars} 字`}
            autoSize={{ minRows: 2, maxRows: 4 }}
            maxLength={narrationMaxChars}
            showCount
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
    [storyboard, projectId, narrationMaxChars]
  )

  const uploadView = (
    <div className="storyboard-studio-config">
      {generating && (
        <Alert
          type="info"
          showIcon
          message="正在 AI 生成分镜表，通常需要 1–3 分钟…"
          style={{ marginBottom: 12 }}
        />
      )}
      <Spin spinning={uploadingVideos}>
      <div
        className={`storyboard-upload-zone ${dragOver ? 'drag-over' : ''} ${hasUploadedVideos ? 'has-files' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (e.dataTransfer.files.length) void uploadVideoFiles(e.dataTransfer.files)
        }}
        onClick={() => !uploadingVideos && videoInputRef.current?.click()}
      >
        <CloudUploadOutlined className="storyboard-upload-icon" />
        <div className="storyboard-upload-title">
          {uploadingVideos
            ? '正在上传视频…'
            : hasUploadedVideos
              ? '继续添加视频（可多次上传）'
              : '点击或拖拽 MP4 到此处上传'}
        </div>
        <Text type="secondary" className="storyboard-upload-hint">
          支持多选；上传后立即保存；无字幕时将自动语音识别
        </Text>
      </div>

      <input
        ref={videoInputRef}
        type="file"
        accept="video/*,.mp4"
        multiple
        hidden
        disabled={uploadingVideos}
        onChange={(e) => {
          if (e.target.files?.length) void uploadVideoFiles(e.target.files)
        }}
      />

      {hasUploadedVideos && (
        <div className="storyboard-upload-records">
          <div className="storyboard-upload-records-header">
            <Text strong>已上传记录</Text>
            <Tag color="blue">{videoSources.length} 个视频</Tag>
          </div>
          <div className="storyboard-upload-records-list">
            {videoSources.map((source, index) => (
              <div key={source.id} className="storyboard-upload-record-item">
                <div className="storyboard-upload-record-main">
                  <Tag color="processing">{index + 1}</Tag>
                  <div className="storyboard-upload-record-text">
                    <Text ellipsis className="storyboard-upload-record-name">
                      {source.original_name}
                    </Text>
                    <Text type="secondary" className="storyboard-upload-record-meta">
                      {formatFileSize(source.size)} · {dayjs(source.uploaded_at).format('MM-DD HH:mm')}
                    </Text>
                  </div>
                </div>
                <Popconfirm
                  title="删除此视频？"
                  description="删除后会重新合并剩余视频"
                  onConfirm={() => void handleDeleteVideoSource(source.id)}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </div>
            ))}
          </div>
        </div>
      )}
      </Spin>

      <div className="storyboard-studio-config-grid">
        <section className="storyboard-config-section">
          <Text className="storyboard-config-section-title">生成设置</Text>
          <div className="storyboard-config-section-body storyboard-config-section-body--main">
            <div className="storyboard-config-field">
              <Text type="secondary">推理模型</Text>
              <Select
                value={selectedModel || undefined}
                onChange={setSelectedModel}
                options={modelOptions}
                className="storyboard-config-control"
                placeholder="选择推理模型"
                loading={modelOptions.length === 0 && !selectedModel}
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">
                旁白文风{' '}
                <Tooltip title="控制旁白文字的写法风格，不是配音或原声设置">
                  <QuestionCircleOutlined className="storyboard-config-help-icon" />
                </Tooltip>
              </Text>
              <Select
                value={normalizeVoiceStyle(voiceStyle)}
                onChange={setVoiceStyle}
                options={NARRATION_STYLE_PRESETS}
                className="storyboard-config-control"
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">默认要求</Text>
              <Select
                value={requirementPreset}
                onChange={setRequirementPreset}
                options={REQUIREMENT_PRESETS}
                className="storyboard-config-control"
              />
            </div>
          </div>
        </section>

        <section className="storyboard-config-section">
          <Text className="storyboard-config-section-title">成片参数</Text>
          <div className="storyboard-config-section-body storyboard-config-section-body--metrics">
            <div className="storyboard-config-field">
              <Text type="secondary">成片占比</Text>
              <InputNumber
                min={0.1}
                max={1}
                step={0.1}
                value={durationRatio}
                onChange={(v) => setDurationRatio(v ?? 0.5)}
                addonAfter={`${Math.round(durationRatio * 100)}%`}
                className="storyboard-config-control storyboard-config-control--number"
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">分镜数量</Text>
              <InputNumber
                min={4}
                max={30}
                value={maxShots}
                onChange={(v) => setMaxShots(v ?? 10)}
                className="storyboard-config-control storyboard-config-control--number"
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">旁白字数</Text>
              <InputNumber
                min={4}
                max={80}
                value={narrationMaxChars}
                onChange={(v) => setNarrationMaxChars(v ?? 10)}
                addonAfter="字"
                className="storyboard-config-control storyboard-config-control--number"
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">爆款开头</Text>
              <Select
                value={goldenOpening ? 'viral_5s' : 'normal'}
                onChange={(v) => setGoldenOpening(v === 'viral_5s')}
                options={GOLDEN_PRESETS}
                className="storyboard-config-control"
              />
            </div>
            <div className="storyboard-config-field">
              <Text type="secondary">画幅比例</Text>
              <Select
                value={aspectRatio}
                onChange={setAspectRatio}
                options={[
                  { value: '9:16', label: '9:16 竖屏' },
                  { value: '16:9', label: '16:9 横屏' },
                ]}
                className="storyboard-config-control"
              />
            </div>
          </div>
        </section>
      </div>

        <TextArea
          rows={2}
          className="storyboard-config-custom-prompt"
          placeholder="补充自定义要求（选填，仅填写你自己的说明；旁白文风由上方选项控制）"
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
        />

        <div className="storyboard-studio-file-row">
          <input
            ref={srtInputRef}
            type="file"
            accept=".srt"
            hidden
            onChange={(e) => setSrtFile(e.target.files?.[0] || null)}
          />
          <Button icon={<FileTextOutlined />} onClick={() => srtInputRef.current?.click()}>
            {srtFile ? `字幕：${srtFile.name}` : '导入字幕（可选）'}
          </Button>
        </div>

        <div className="storyboard-studio-advanced">
          <Text type="secondary">对齐选项</Text>
          <Space wrap>
            <Switch checked={sceneAlign} onChange={setSceneAlign} />
            <Text>场景对齐</Text>
            <Switch checked={subtitleAlign} onChange={setSubtitleAlign} />
            <Text>字幕对齐</Text>
          </Space>
        </div>

        <div className="storyboard-studio-actions">
          <Button
            type="primary"
            size="large"
            icon={<SendOutlined />}
            loading={generating}
            disabled={!projectId || !hasUploadedVideos}
            onClick={handleGenerate}
          >
            {generating ? '正在生成分镜…' : hasShots ? '重新生成分镜' : '生成分镜表'}
          </Button>
          {hasShots && (
            <Button size="large" onClick={() => goToStep(1)}>
              查看分镜表
            </Button>
          )}
        </div>
      </div>
  )

  const storyboardStatusHint = useMemo(() => {
    if (!storyboard) return '上传素材并生成分镜表后，可在此编辑旁白并导出成片'
    if (hasUnsavedChanges) return '你有未保存的修改，导出前会自动保存'
    if (storyboard.status === 'completed') return '成片已就绪，可再次导出或下载'
    if (storyboard.status === 'rendering' || rendering) return '正在渲染视频，请稍候…'
    if (storyboard.status === 'failed') return storyboard.error_message || '上次导出失败，请重试'
    return '编辑旁白后，点击「导出视频」生成成片'
  }, [storyboard, hasUnsavedChanges, rendering])

  const storyboardView = (
    <>
      <Alert
        className="storyboard-status-banner"
        type={
          storyboard?.status === 'failed'
            ? 'error'
            : hasUnsavedChanges
              ? 'warning'
              : storyboard?.status === 'completed'
                ? 'success'
                : 'info'
        }
        showIcon
        message={storyboardStatusHint}
        action={
          storyboard?.status === 'completed' && projectId ? (
            <Space>
              <Button
                size="small"
                icon={<UploadOutlined />}
                loading={preparingUpload}
                onClick={() => void handleOpenUpload()}
              >
                投稿
              </Button>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={() => void downloadStoryboardVideo(storyboard)}
              >
                下载成片
              </Button>
            </Space>
          ) : undefined
        }
      />

      <div className="storyboard-studio-toolbar">
        <div className="storyboard-toolbar-main">
          <Button icon={<ArrowLeftOutlined />} onClick={() => goToStep(0)}>
            返回配置
          </Button>
          <Divider type="vertical" className="storyboard-toolbar-divider" />
          <div className="storyboard-toolbar-actions">
            <Button.Group className="storyboard-export-group">
              <Button
                type="primary"
                className="storyboard-btn-export"
                icon={<DownloadOutlined />}
                loading={rendering}
                onClick={() => void handleExportVideo(hasNarrationText)}
              >
                导出视频
              </Button>
              <Dropdown menu={exportMenu} trigger={['click']}>
                <Button
                  type="primary"
                  className="storyboard-btn-export-caret"
                  icon={<DownOutlined />}
                  loading={rendering}
                />
              </Dropdown>
            </Button.Group>
            <Button
              icon={<UploadOutlined />}
              loading={preparingUpload}
              disabled={storyboard?.status !== 'completed'}
              onClick={() => void handleOpenUpload()}
            >
              投稿
            </Button>
            <Badge dot={hasUnsavedChanges}>
              <Button icon={<EditOutlined />} loading={saving} onClick={handleSaveShots}>
                保存修改
              </Button>
            </Badge>
            <Tooltip title="批量修改各镜头的旁白">
              <Dropdown menu={copyToolsMenu}>
                <Button icon={<EditOutlined />}>旁白编辑</Button>
              </Dropdown>
            </Tooltip>
          </div>
        </div>
        <div className="storyboard-toolbar-extra">
          {storyboard && (
            <>
              <Tag color={STATUS_MAP[storyboard.status]?.color || 'default'}>
                {STATUS_MAP[storyboard.status]?.text || storyboard.status}
              </Tag>
              <Tag color="blue">{storyboard.shot_count || editedShots.length} 镜</Tag>
              {storyboard.total_duration ? <Tag>{storyboard.total_duration}s</Tag> : null}
            </>
          )}
        </div>
      </div>

      {!storyboard || !hasShots ? (
        <Empty
          className="storyboard-empty"
          description="还没有分镜表"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button type="primary" onClick={() => goToStep(0)}>
            去上传并生成
          </Button>
        </Empty>
      ) : (
        <div className="storyboard-table-wrap">
          <Table
            rowKey="id"
            columns={columns}
            dataSource={editedShots}
            pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
            loading={generating}
          />
        </div>
      )}
    </>
  )

  return (
    <div className="storyboard-studio">
      <div className="storyboard-studio-header">
        <div className="storyboard-studio-header-main">
          <VideoCameraOutlined className="storyboard-studio-header-icon" />
          <div className="storyboard-studio-header-title">
            <Input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              bordered={false}
              placeholder="输入项目名称"
              style={{ fontWeight: 600, fontSize: 16, padding: 0 }}
              prefix={<EditOutlined style={{ color: '#9aa5b1' }} />}
            />
            {projectId && (
              <Text type="secondary" className="storyboard-studio-header-sub">
                {hasShots
                  ? `分镜 ${editedShots.length} 镜`
                  : hasUploadedVideos
                    ? `已上传 ${videoSources.length} 个视频`
                    : '素材配置中'}
              </Text>
            )}
          </div>
        </div>
        <Space wrap>
          <Badge count={historyProjects.length} size="small" offset={[-2, 2]}>
            <Button icon={<HistoryOutlined />} onClick={() => setHistoryDrawerOpen(true)}>
              混剪项目
            </Button>
          </Badge>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleNewProject}>
            新建项目
          </Button>
        </Space>
      </div>

      <Steps
        className="storyboard-studio-steps"
        current={currentStep}
        onChange={(step) => goToStep(step as 0 | 1)}
        items={[
          {
            title: '上传素材',
            description: generating ? '生成中…' : '配置并生成分镜',
            disabled: generating,
          },
          {
            title: '编辑分镜',
            description: hasShots ? `${editedShots.length} 个镜头` : '编辑旁白并导出',
            disabled: !hasShots && !generating,
          },
        ]}
      />

      <div className="storyboard-studio-body">
        {subTab === 'upload' ? uploadView : storyboardView}
      </div>

      <Modal
        title="查找并替换旁白"
        open={replaceModalOpen}
        onCancel={() => setReplaceModalOpen(false)}
        onOk={handleBatchReplace}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Text type="secondary">
            在所有镜头的旁白中批量替换文字，例如统一修改人名或用词。
          </Text>
          <Input placeholder="查找内容，如：男主" value={replaceFind} onChange={(e) => setReplaceFind(e.target.value)} />
          <Input placeholder="替换为，如：他" value={replaceWith} onChange={(e) => setReplaceWith(e.target.value)} />
        </Space>
      </Modal>

      <Modal
        title={exportWithNarration ? '导出视频（带旁白字幕）' : '导出视频（纯画面）'}
        open={exportModalOpen}
        footer={
          exportPhase === 'error' ? (
            <Space>
              <Button onClick={() => setExportModalOpen(false)}>关闭</Button>
              <Button type="primary" onClick={() => void handleExportVideo(exportWithNarration)}>
                重试
              </Button>
            </Space>
          ) : exportPhase === 'done' ? (
            <Space>
              <Button onClick={() => setExportModalOpen(false)}>完成</Button>
              <Button type="primary" icon={<UploadOutlined />} onClick={() => void handleOpenUpload()}>
                立即投稿
              </Button>
            </Space>
          ) : null
        }
        closable={exportPhase !== 'save' && exportPhase !== 'render' && exportPhase !== 'download'}
        maskClosable={false}
        onCancel={() => {
          if (!rendering) setExportModalOpen(false)
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Progress
            percent={exportProgressPercent}
            status={exportPhase === 'error' ? 'exception' : exportPhase === 'done' ? 'success' : 'active'}
          />
          <Text type={exportPhase === 'error' ? 'danger' : 'secondary'}>
            {exportPhase === 'error'
              ? exportError
              : exportPhase === 'render' && exportWithNarration
                ? '正在合成旁白字幕视频，请稍候…'
                : EXPORT_PHASE_LABEL[exportPhase]}
          </Text>
        </Space>
      </Modal>

      <Drawer
        title="混剪项目"
        placement="right"
        width={380}
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        className="storyboard-history-drawer"
        extra={
          <Button type="link" size="small" onClick={() => void loadHistory()}>
            刷新
          </Button>
        }
        footer={
          <Button type="primary" block icon={<PlusOutlined />} onClick={handleNewProject}>
            新建项目
          </Button>
        }
      >
        <Input
          allowClear
          prefix={<SearchOutlined style={{ color: '#9aa5b1' }} />}
          placeholder="搜索项目名称"
          value={historySearch}
          onChange={(e) => setHistorySearch(e.target.value)}
          className="storyboard-history-search"
        />
        <Spin spinning={historyLoading}>
          {filteredHistoryProjects.length === 0 && !historyLoading ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={historySearch ? '没有匹配的项目' : '暂无混剪项目'}
              className="storyboard-history-drawer-empty"
            >
              {!historySearch && (
                <Button type="primary" onClick={handleNewProject}>
                  创建第一个项目
                </Button>
              )}
            </Empty>
          ) : (
            <List
              className="storyboard-history-list"
              dataSource={filteredHistoryProjects}
              renderItem={(item) => {
                const status = item.storyboard_status
                  ? STATUS_MAP[item.storyboard_status]
                  : null
                const isActive = projectId === item.project_id
                return (
                  <List.Item
                    className={`storyboard-history-list-item${isActive ? ' active' : ''}`}
                    onClick={() => void openHistoryProject(item)}
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="删除此混剪项目？"
                        description="将同时删除分镜与导出文件"
                        onConfirm={() => void handleDeleteHistoryProject(item)}
                        onCancel={(e) => e?.stopPropagation()}
                      >
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <div className="storyboard-history-list-content">
                      <div className="storyboard-history-list-thumb">
                        {item.thumbnail ? (
                          <img src={item.thumbnail} alt="" />
                        ) : (
                          <VideoCameraOutlined />
                        )}
                      </div>
                      <div className="storyboard-history-list-meta">
                        <Text strong ellipsis className="storyboard-history-list-title">
                          {item.name}
                        </Text>
                        <Text type="secondary" className="storyboard-history-list-desc">
                          {dayjs(item.updated_at).fromNow()}
                          {item.shot_count > 0 ? ` · ${item.shot_count} 镜` : ''}
                          {item.total_duration ? ` · ${item.total_duration}s` : ''}
                        </Text>
                        <Space size={4} wrap className="storyboard-history-list-tags">
                          {status ? (
                            <Tag color={status.color}>{status.text}</Tag>
                          ) : (
                            <Tag>未生成分镜</Tag>
                          )}
                          {isActive ? <Tag color="green">当前</Tag> : null}
                        </Space>
                      </div>
                      <RightOutlined className="storyboard-history-list-arrow" />
                    </div>
                  </List.Item>
                )
              }}
            />
          )}
        </Spin>
      </Drawer>

      {projectId && uploadClipId ? (
        <UploadModal
          visible={uploadModalOpen}
          onCancel={() => setUploadModalOpen(false)}
          projectId={projectId}
          clipIds={[uploadClipId]}
          clipTitles={[uploadClipTitle || storyboard?.name || projectName]}
          onSuccess={() => {
            message.success('投稿任务已提交')
            setUploadModalOpen(false)
          }}
        />
      ) : null}
    </div>
  )
}

export default StoryboardStudio
