import { useCallback, useState } from 'react'
import {
  type PickerSettings,
  readSettings,
  writeSettings,
} from './settings'

export function useSettings() {
  const [settings, setSettings] = useState<PickerSettings>(() => readSettings())

  const update = useCallback((patch: Partial<PickerSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch }
      writeSettings(next)
      return next
    })
  }, [])

  return { settings, update }
}
