import { useEffect, useState } from 'react'

export type Device = 'phone' | 'tablet' | 'desktop'

const COUNTS: Record<Device, number> = {
  phone: 4,
  tablet: 6,
  desktop: 9,
}

function classify(width: number): Device {
  if (width < 640) return 'phone'
  if (width < 1024) return 'tablet'
  return 'desktop'
}

export function useDevice(): Device {
  const [device, setDevice] = useState<Device>('phone')

  useEffect(() => {
    const apply = () => setDevice(classify(window.innerWidth))
    apply()
    window.addEventListener('resize', apply)
    return () => window.removeEventListener('resize', apply)
  }, [])

  return device
}

export function recommendationCount(device: Device): number {
  return COUNTS[device]
}
