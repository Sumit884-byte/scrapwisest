import { useCallback, useEffect, useState } from 'react'
import type { TfRegion } from './region'
import {
  nearestRegion,
  readStoredDenied,
  readStoredRegion,
  writeStoredDenied,
  writeStoredRegion,
} from './region'

export type RegionStatus = 'idle' | 'asking' | 'ready' | 'denied'

export function useRegion() {
  const [region, setRegion] = useState<TfRegion | null>(() => readStoredRegion())
  const [status, setStatus] = useState<RegionStatus>(() => {
    if (readStoredRegion()) return 'ready'
    if (readStoredDenied()) return 'denied'
    return 'idle'
  })

  const applyCoords = useCallback((lat: number, lng: number) => {
    const next = nearestRegion(lat, lng)
    writeStoredRegion(next.id)
    setRegion(next)
    setStatus('ready')
    return next
  }, [])

  const request = useCallback(async () => {
    if (!navigator.geolocation) {
      writeStoredDenied()
      setStatus('denied')
      return null
    }
    setStatus('asking')
    return new Promise<TfRegion | null>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          resolve(applyCoords(pos.coords.latitude, pos.coords.longitude))
        },
        () => {
          writeStoredDenied()
          setStatus('denied')
          resolve(null)
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 3_600_000 },
      )
    })
  }, [applyCoords])

  useEffect(() => {
    if (status !== 'idle') return
    if (!navigator.permissions?.query) return
    void navigator.permissions
      .query({ name: 'geolocation' })
      .then((result) => {
        if (result.state === 'granted') void request()
      })
      .catch(() => {
        /* Permissions API is optional */
      })
  }, [request, status])

  return { region, status, request }
}
