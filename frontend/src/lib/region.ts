/** Token Factory regions that host a Nemotron we can use for everyday chat. */

export interface TfRegion {
  id: 'eu-north1' | 'us-central1'
  label: string
  lat: number
  lng: number
}

export const TF_REGIONS: readonly TfRegion[] = [
  { id: 'eu-north1', label: 'Europe', lat: 60.1699, lng: 24.9384 },
  { id: 'us-central1', label: 'US Central', lat: 41.2619, lng: -95.8608 },
]

export const REGION_STORAGE_KEY = 'scrapwisest.tf_region'

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const r = 6371
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)))
}

export function nearestRegion(lat: number, lng: number): TfRegion {
  return TF_REGIONS.reduce((best, next) =>
    haversineKm(lat, lng, next.lat, next.lng) < haversineKm(lat, lng, best.lat, best.lng)
      ? next
      : best,
  )
}

export function regionById(id: string | null | undefined): TfRegion | null {
  if (!id) return null
  return TF_REGIONS.find((r) => r.id === id) ?? null
}

export function readStoredRegion(): TfRegion | null {
  try {
    return regionById(localStorage.getItem(REGION_STORAGE_KEY))
  } catch {
    return null
  }
}

export function writeStoredRegion(id: TfRegion['id']): void {
  try {
    localStorage.setItem(REGION_STORAGE_KEY, id)
  } catch {
    /* private mode */
  }
}

export function readStoredDenied(): boolean {
  try {
    return localStorage.getItem(`${REGION_STORAGE_KEY}.denied`) === '1'
  } catch {
    return false
  }
}

export function writeStoredDenied(): void {
  try {
    localStorage.setItem(`${REGION_STORAGE_KEY}.denied`, '1')
  } catch {
    /* ignore */
  }
}
