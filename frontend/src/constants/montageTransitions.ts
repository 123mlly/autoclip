export const MONTAGE_TRANSITION_OPTIONS = [
  { value: 'none', label: '硬切' },
  { value: 'fade', label: '淡入淡出' },
  { value: 'fadeblack', label: '黑场过渡' },
  { value: 'fadewhite', label: '闪白' },
  { value: 'wipeleft', label: '左划' },
  { value: 'wiperight', label: '右划' },
  { value: 'wipeup', label: '上划' },
  { value: 'wipedown', label: '下划' },
  { value: 'slideleft', label: '左滑' },
  { value: 'slideright', label: '右滑' },
  { value: 'slideup', label: '上滑' },
  { value: 'slidedown', label: '下滑' },
  { value: 'circleopen', label: '圆形展开' },
  { value: 'circleclose', label: '圆形收缩' },
  { value: 'dissolve', label: '溶解' },
] as const

export function estimateMontageDuration(
  segments: Array<{
    in_offset?: number
    out_offset?: number | null
    transition?: string
    transition_duration?: number
  }>,
  clipDurations: Map<string, number>,
  resolveKey: (segment: { clip_id: string; project_id?: string }) => string
): number {
  let total = 0
  segments.forEach((segment, index) => {
    const key = resolveKey(segment as { clip_id: string; project_id?: string })
    const clipDuration = clipDurations.get(key) || 0
    const inOffset = Number(segment.in_offset || 0)
    const outOffset =
      segment.out_offset === null || segment.out_offset === undefined
        ? clipDuration
        : Number(segment.out_offset)
    total += Math.max(0.1, outOffset - inOffset)
    if (index > 0 && segment.transition && segment.transition !== 'none') {
      total -= Number(segment.transition_duration ?? 0.5)
    }
  })
  return Math.max(0, total)
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const rest = s % 60
  return m > 0 ? `${m}分${rest}秒` : `${rest}秒`
}
