/**
 * Step 5 contract tests: the frontend consumes the generic backend contract
 * (total_price / price_per_kg / currency / country / city / neighborhood /
 * estimate tier) with no PKR-specific assumptions.
 */
import { describe, expect, it } from 'vitest'
import {
  compareSalePerKg,
  estimateSampleCount,
  evidenceSalesText,
  formatMoney,
  formatPerKg,
  isKnownCurrency,
  isSalePendingReview,
  isSaleTrusted,
  pendingSaleText,
  reportPlace,
  reportPlaceLabel,
  tierLabel,
  trustedSaleText,
  verdictEvidenceCount,
} from './market'
import type { PriceData, ReportData } from './types'

function report(overrides: Partial<ReportData>): ReportData {
  return {
    material_type: 'copper',
    quantity_kg: 10,
    total_price: 500,
    price_per_kg: 50,
    currency: 'PKR',
    country: null,
    city: null,
    neighborhood: null,
    location: null,
    needs_confirmation: false,
    is_anomalous: false,
    ...overrides,
  }
}

// The card renders through these helpers, so asserting the helpers asserts
// what the user sees (no hardcoded PKR, no field substitution).
function reportCardText(data: ReportData): { total: string; perKg: string; place: string } {
  return {
    total: formatMoney(data.total_price, data.currency),
    perKg: formatPerKg(data.price_per_kg, data.currency),
    place: reportPlaceLabel(data),
  }
}

describe('sale/report totals use the backend currency', () => {
  it('Pakistan renders PKR', () => {
    const card = reportCardText(report({ total_price: 500, currency: 'PKR' }))
    expect(card.total).toBe('PKR 500')
  })

  it('India renders INR (never PKR)', () => {
    const card = reportCardText(report({ total_price: 500, currency: 'INR' }))
    expect(card.total).toBe('INR 500')
    expect(card.total).not.toContain('PKR')
  })

  it('USA renders USD', () => {
    const card = reportCardText(report({ total_price: 12, currency: 'USD' }))
    expect(card.total).toBe('USD 12')
  })

  it('lowercase currency codes are normalized for display', () => {
    expect(formatMoney(500, 'pkr')).toBe('PKR 500')
    expect(formatMoney(500, 'inr')).toBe('INR 500')
  })
})

describe('price per kg uses price_per_kg', () => {
  it('renders PKR per-kg from the generic field', () => {
    expect(formatPerKg(180, 'PKR')).toBe('PKR 180/kg')
  })

  it('renders INR per-kg', () => {
    expect(formatPerKg(95, 'INR')).toBe('INR 95/kg')
  })

  it('renders USD per-kg with decimals', () => {
    expect(formatPerKg(2.4, 'USD')).toBe('USD 2.4/kg')
  })

  it('report cards read price_per_kg (not a legacy PKR field)', () => {
    const data = report({ price_per_kg: 350, currency: 'PKR' })
    // The ReportData contract has no legacy key at all.
    expect('price_paid_pkr_per_kg' in data).toBe(false)
    expect(reportCardText(data).perKg).toBe('PKR 350/kg')
  })
})

describe('Step 8 report examples', () => {
  it('Pakistan copper report renders PKR + full place', () => {
    const card = reportCardText(
      report({
        material_type: 'copper',
        quantity_kg: 10,
        total_price: 3500,
        price_per_kg: 350,
        currency: 'PKR',
        country: 'Pakistan',
        city: 'Multan',
        neighborhood: 'Income Colony',
      }),
    )
    expect(card.total).toBe('PKR 3500')
    expect(card.perKg).toBe('PKR 350/kg')
    expect(card.place).toBe('Income Colony, Multan, Pakistan')
  })

  it('India copper report renders INR and never PKR', () => {
    const card = reportCardText(
      report({
        material_type: 'copper',
        quantity_kg: 10,
        total_price: 900,
        price_per_kg: 90,
        currency: 'INR',
        country: 'India',
        city: 'Delhi',
        neighborhood: 'Karol Bagh',
      }),
    )
    expect(card.total).toBe('INR 900')
    expect(card.perKg).toBe('INR 90/kg')
    expect(card.place).toBe('Karol Bagh, Delhi, India')
    expect(`${card.total} ${card.perKg}`).not.toContain('PKR')
  })
})

describe('estimate tier labels follow the backend tier_used', () => {
  it('maps every real backend tier distinctly (en)', () => {
    expect(tierLabel('local', 'en')).toBe('Neighborhood reports')
    expect(tierLabel('local+city', 'en')).toBe('Neighborhood + city reports')
    expect(tierLabel('city', 'en')).toBe('Wider-area reports')
    expect(tierLabel('country', 'en')).toBe('Country/market reports')
    expect(tierLabel('seed', 'en')).toBe('Seed market baseline')
    expect(tierLabel('unavailable', 'en')).toBe('No estimate available')
  })

  it('never shows country as a seed estimate', () => {
    expect(tierLabel('country', 'en')).not.toBe(tierLabel('seed', 'en'))
  })

  it('never presents unavailable as a valid seed estimate', () => {
    expect(tierLabel('unavailable', 'en')).not.toBe(tierLabel('seed', 'en'))
    expect(tierLabel('unavailable', 'en')).toMatch(/no estimate/i)
  })

  it('maps every real backend tier distinctly (hi)', () => {
    const labels = new Set([
      tierLabel('local', 'hi'),
      tierLabel('local+city', 'hi'),
      tierLabel('city', 'hi'),
      tierLabel('country', 'hi'),
      tierLabel('seed', 'hi'),
      tierLabel('unavailable', 'hi'),
    ])
    expect(labels.size).toBe(6)
  })
})

describe('missing currency never becomes PKR', () => {
  it.each([undefined, null, '', '  ', 'unknown', 'UNKNOWN'])(
    'falls back to the bare amount for %p',
    (currency) => {
      expect(formatMoney(500, currency)).toBe('500')
      expect(formatPerKg(180, currency)).toBe('180/kg')
      expect(isKnownCurrency(currency)).toBe(false)
    },
  )

  it('does not contain PKR anywhere in the fallback', () => {
    expect(formatMoney(500, null)).not.toContain('PKR')
    expect(formatMoney(500, 'unknown')).not.toContain('PKR')
  })
})

describe('missing location fabricates nothing', () => {
  it('returns null / Unknown when nothing is known', () => {
    expect(reportPlace({})).toBeNull()
    expect(reportPlace({ location: 'unknown' })).toBeNull()
    expect(reportPlace({ location: 'Unknown' })).toBeNull()
    expect(reportPlaceLabel({})).toBe('Unknown')
  })

  it('composes only the fields that exist', () => {
    expect(reportPlace({ city: 'Delhi', country: 'India' })).toBe('Delhi, India')
    expect(reportPlace({ neighborhood: 'Karol Bagh' })).toBe('Karol Bagh')
  })

  it('falls back to a meaningful legacy location string', () => {
    expect(reportPlace({ location: 'Samejabad' })).toBe('Samejabad')
  })
})

describe('plain-language trust + evidence for the Sale Verdict card', () => {
  const BANNED = [
    'Confidence',
    'confidence',
    'tier_used',
    'PriceEvidence',
    'Isolation Forest',
    'freshness_days',
    'tier = seed',
    'tier=seed',
  ]

  function price(overrides: Partial<PriceData>): PriceData {
    return {
      material_type: 'plastic_pet',
      location: 'Income Colony',
      estimated_price_per_kg: 180,
      currency: 'PKR',
      confidence: 0.8,
      tier_used: 'local',
      local_report_count: 4,
      city_report_count: 6,
      country_report_count: 10,
      evidence: {
        source: 'reports',
        scope: 'neighborhood',
        report_count: 4,
        currency: 'PKR',
        country: 'Pakistan',
        freshness_days: 30,
        seed_source: null,
      },
      ...overrides,
    }
  }

  it('accepted report + 4 evidence reports shows trust + plural evidence', () => {
    const sale = report({ needs_confirmation: false, is_anomalous: false })
    expect(isSaleTrusted(sale)).toBe(true)
    expect(isSalePendingReview(sale)).toBe(false)
    expect(trustedSaleText('en')).toBe('Saved and counted in local rates.')
    expect(evidenceSalesText(price({}), 'en')).toBe('Based on 4 recent local sales')
  })

  it('accepted report + 1 evidence report uses singular wording', () => {
    const data = price({
      local_report_count: 1,
      city_report_count: 1,
      evidence: {
        source: 'reports',
        scope: 'neighborhood',
        report_count: 1,
        currency: 'PKR',
        country: 'Pakistan',
        freshness_days: 30,
        seed_source: null,
      },
    })
    expect(verdictEvidenceCount(data)).toBe(1)
    expect(evidenceSalesText(data, 'en')).toBe('Based on 1 recent local sale')
  })

  it('pending/unusual report shows plain language and no technical terms', () => {
    const pending = report({ needs_confirmation: true, is_anomalous: false })
    const flagged = report({ needs_confirmation: false, is_anomalous: true })
    for (const sale of [pending, flagged]) {
      expect(isSalePendingReview(sale)).toBe(true)
      expect(isSaleTrusted(sale)).toBe(false)
    }
    const text = pendingSaleText('en')
    expect(text).toMatch(/isn't counted in local prices yet/i)
    expect(text).toMatch(/unusual/i)
    for (const term of BANNED) {
      expect(trustedSaleText('en')).not.toContain(term)
      expect(pendingSaleText('en')).not.toContain(term)
      expect(evidenceSalesText(price({}), 'en') ?? '').not.toContain(term)
    }
    // The card must not surface raw backend reasons; helpers never echo them.
    const rawReason =
      'deterministic anomaly check: price/kg (999) outside expected range for plastic_pet'
    expect(pendingSaleText('en')).not.toContain('deterministic')
    expect(pendingSaleText('en')).not.toContain(rawReason.slice(0, 20))
  })

  it('seed estimate keeps the existing early-estimate behavior', () => {
    const verdict = compareSalePerKg(
      { material_type: 'plastic_pet', price_per_kg: 150, currency: 'PKR' },
      {
        material_type: 'plastic_pet',
        estimated_price_per_kg: 180,
        currency: 'PKR',
        tier_used: 'seed',
      },
    )
    expect(verdict.status).toBe('seed')
    expect(verdict.typicalPerKg).toBe(180)
    // Seed never claims local-sales evidence.
    expect(
      verdictEvidenceCount(price({ tier_used: 'seed', evidence: { source: 'seed', scope: 'seed', report_count: 0, currency: 'PKR', country: 'Pakistan', freshness_days: 30, seed_source: 'verified' } })),
    ).toBeNull()
    expect(evidenceSalesText(price({ tier_used: 'seed' }), 'en')).toBeNull()
  })

  it('unavailable estimate keeps the existing no-comparison behavior', () => {
    const verdict = compareSalePerKg(
      { material_type: 'plastic_pet', price_per_kg: 150, currency: 'PKR' },
      {
        material_type: 'plastic_pet',
        estimated_price_per_kg: 0,
        currency: 'PKR',
        tier_used: 'unavailable',
      },
    )
    expect(verdict.status).toBe('unavailable')
    expect(verdict.typicalPerKg).toBeNull()
    expect(verdict.diffPerKg).toBeNull()
  })

  it('no evidence count does not invent a report count', () => {
    expect(
      verdictEvidenceCount(
        price({
          tier_used: 'local',
          local_report_count: 0,
          city_report_count: 0,
          country_report_count: 0,
          evidence: {
            source: 'reports',
            scope: 'neighborhood',
            report_count: 0,
            currency: 'PKR',
            country: 'Pakistan',
            freshness_days: 30,
            seed_source: null,
          },
        }),
      ),
    ).toBeNull()
    expect(
      evidenceSalesText(
        price({
          tier_used: 'local',
          local_report_count: 0,
          city_report_count: 0,
          country_report_count: 0,
          evidence: {
            source: 'reports',
            scope: 'neighborhood',
            report_count: 0,
            currency: 'PKR',
            country: 'Pakistan',
            freshness_days: 30,
            seed_source: null,
          },
        }),
        'en',
      ),
    ).toBeNull()
  })

  it('existing Sale Verdict comparison behavior is unchanged', () => {
    const verdict = compareSalePerKg(
      { material_type: 'plastic_pet', price_per_kg: 150, currency: 'PKR' },
      {
        material_type: 'plastic_pet',
        estimated_price_per_kg: 180,
        currency: 'PKR',
        tier_used: 'local',
      },
    )
    expect(verdict.status).toBe('ok')
    expect(verdict.diffPerKg).toBe(-30)
    expect(verdict.direction).toBe('less')
    const mismatch = compareSalePerKg(
      { material_type: 'plastic_pet', price_per_kg: 150, currency: 'PKR' },
      {
        material_type: 'plastic_pet',
        estimated_price_per_kg: 180,
        currency: 'INR',
        tier_used: 'local',
      },
    )
    expect(mismatch.status).toBe('not-comparable')
  })
})

describe('estimate sample counts respect the tier scope', () => {
  it('country estimates use the country/market count', () => {
    const data: PriceData = {
      material_type: 'copper',
      location: 'Delhi',
      estimated_price_per_kg: 90,
      currency: 'INR',
      confidence: 0.5,
      tier_used: 'country',
      local_report_count: 0,
      city_report_count: 1,
      country_report_count: 8,
    }
    expect(estimateSampleCount(data)).toBe(8)
  })

  it('city estimates prefer the city count', () => {
    expect(
      estimateSampleCount({
        tier_used: 'city',
        local_report_count: 1,
        city_report_count: 4,
        country_report_count: 9,
      }),
    ).toBe(4)
  })
})
