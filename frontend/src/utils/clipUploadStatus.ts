import { UploadRecord } from '../services/uploadApi'
import { YouTubeUploadRecord } from '../services/youtubeUploadApi'

export type UploadPlatform = 'bilibili' | 'youtube'

export interface PlatformUploadStatus {
  platform: UploadPlatform
  status: string
  progress: number
  bvid?: string
  video_url?: string
  error_message?: string
  record_id: string | number
}

export interface ClipUploadStatus {
  bilibili?: PlatformUploadStatus
  youtube?: PlatformUploadStatus
}

export type ClipUploadStatusMap = Record<string, ClipUploadStatus>

export function recordMatchesClip(recordClipId: string | undefined, clipId: string): boolean {
  if (!recordClipId) return false
  return recordClipId
    .split(',')
    .map((s) => s.trim())
    .includes(clipId)
}

export function isUploadSuccess(status: string): boolean {
  return status === 'success' || status === 'completed'
}

export function isUploadActive(status: string): boolean {
  return status === 'pending' || status === 'processing'
}

function pickLatestForClip<T extends { clip_id?: string; created_at: string }>(
  records: T[],
  clipId: string
): T | undefined {
  return records
    .filter((r) => recordMatchesClip(r.clip_id, clipId))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]
}

export function buildClipUploadStatusMap(
  bilibiliRecords: UploadRecord[],
  youtubeRecords: YouTubeUploadRecord[]
): ClipUploadStatusMap {
  const clipIds = new Set<string>()

  for (const r of bilibiliRecords) {
    if (r.clip_id) {
      r.clip_id.split(',').forEach((id) => {
        const trimmed = id.trim()
        if (trimmed) clipIds.add(trimmed)
      })
    }
  }
  for (const r of youtubeRecords) {
    if (r.clip_id) {
      r.clip_id.split(',').forEach((id) => {
        const trimmed = id.trim()
        if (trimmed) clipIds.add(trimmed)
      })
    }
  }

  const map: ClipUploadStatusMap = {}

  for (const clipId of clipIds) {
    const bili = pickLatestForClip(bilibiliRecords, clipId)
    const yt = pickLatestForClip(youtubeRecords, clipId)

    const entry: ClipUploadStatus = {}
    if (bili) {
      entry.bilibili = {
        platform: 'bilibili',
        status: bili.status,
        progress: bili.progress ?? 0,
        bvid: bili.bv_id,
        error_message: bili.error_message,
        record_id: bili.id,
      }
    }
    if (yt) {
      entry.youtube = {
        platform: 'youtube',
        status: yt.status,
        progress: yt.progress ?? 0,
        video_url: yt.video_url,
        error_message: yt.error_message,
        record_id: yt.id,
      }
    }
    map[clipId] = entry
  }

  return map
}

export function hasActiveUploads(statusMap: ClipUploadStatusMap): boolean {
  return Object.values(statusMap).some(
    (s) =>
      (s.bilibili && isUploadActive(s.bilibili.status)) ||
      (s.youtube && isUploadActive(s.youtube.status))
  )
}

export function getBilibiliVideoUrl(bvid?: string): string | undefined {
  if (!bvid) return undefined
  const id = bvid.startsWith('BV') ? bvid : `BV${bvid}`
  return `https://www.bilibili.com/video/${id}`
}
