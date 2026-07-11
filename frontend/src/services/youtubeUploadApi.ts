/**
 * YouTube 投稿 API
 */

import api from './api'

export interface YouTubeAccount {
  id: number
  channel_id?: string
  channel_title?: string
  email?: string
  status: string
  is_default: boolean
  upload_count: number
}

export interface YouTubeUploadRequest {
  clip_ids: string[]
  account_id: number
  title: string
  description: string
  tags: string[]
  category_id: string
  privacy_status: 'private' | 'unlisted' | 'public'
}

export interface YouTubeCategory {
  id: string
  name: string
}

export const YOUTUBE_CATEGORIES: YouTubeCategory[] = [
  { id: '22', name: 'People & Blogs' },
  { id: '24', name: 'Entertainment' },
  { id: '23', name: 'Comedy' },
  { id: '10', name: 'Music' },
  { id: '20', name: 'Gaming' },
  { id: '27', name: 'Education' },
  { id: '28', name: 'Science & Technology' },
  { id: '1', name: 'Film & Animation' },
  { id: '26', name: 'Howto & Style' },
  { id: '17', name: 'Sports' },
  { id: '15', name: 'Pets & Animals' },
  { id: '19', name: 'Travel & Events' },
  { id: '25', name: 'News & Politics' },
  { id: '2', name: 'Autos & Vehicles' },
]

export const youtubeUploadApi = {
  getConfig: async (): Promise<{ configured: boolean; message: string }> => {
    return api.get('/youtube-upload/config')
  },

  startOAuth: async (nickname?: string): Promise<{ auth_url: string; state: string }> => {
    return api.get('/youtube-upload/oauth/start', { params: { nickname } })
  },

  importRefreshToken: async (data: {
    refresh_token: string
    client_id?: string
    client_secret?: string
    nickname?: string
  }): Promise<YouTubeAccount> => {
    return api.post('/youtube-upload/accounts/import-refresh-token', data)
  },

  importOAuthCode: async (code: string, nickname?: string): Promise<YouTubeAccount> => {
    return api.post('/youtube-upload/oauth/code', { code, nickname })
  },

  getAccounts: async (): Promise<YouTubeAccount[]> => {
    return api.get('/youtube-upload/accounts')
  },

  deleteAccount: async (accountId: number): Promise<void> => {
    return api.delete(`/youtube-upload/accounts/${accountId}`)
  },

  createUploadTask: async (
    projectId: string,
    data: YouTubeUploadRequest
  ): Promise<{ message: string; record_id: string; clip_count: number }> => {
    return api.post(`/youtube-upload/projects/${projectId}/upload`, data)
  },

  getUploadRecord: async (recordId: string | number): Promise<{
    id: number
    status: string
    video_id?: string
    video_url?: string
    error_message?: string
    progress: number
    title: string
  }> => {
    return api.get(`/youtube-upload/records/${recordId}`)
  },

  getUploadRecords: async (projectId?: string) => {
    return api.get('/youtube-upload/records', { params: projectId ? { project_id: projectId } : {} })
  },

  getCategories: async (): Promise<YouTubeCategory[]> => {
    return api.get('/youtube-upload/categories')
  },
}
