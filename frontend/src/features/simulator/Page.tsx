import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { post } from '@/lib/api'
import { formatMoney, formatNumber } from '@/lib/format'
import { needLabel, usePack } from '@/lib/pack'
import { Button, inputStyle, PageHeader, Panel, Segmented, Stat } from '@/ui/primitives'
import { EmptyState, ErrorState } from '@/ui/states'

type Strategy = 'balanced' | 'reach' | 'equity'

interface Funded {
  priority_id: number
  rank: number
  region_name: string
  sector: string
  score: number
  cost: number
  beneficiaries: number
}

interface Simulation {
  currency: string
  currency_symbol: string
  strategy: Strategy
  budget: number
  total_cost: number
  remaining: number
  beneficiaries: number
  candidates: number
  funded: Funded[]
  audit_count: number
  notes: string[]
}

const STRATEGIES: { value: Strategy; label: string; explain: string }[] = [
  { value: 'balanced', label: 'Balanced', explain: 'Highest priority score per rupee, using the weights in the country pack.' },
  { value: 'reach', label: 'Most people', explain: 'Most unserved households connected per rupee.' },
  { value: 'equity', label: 'Worst-served first', explain: 'Places furthest behind the best-served place, regardless of cost.' },
]

export default function SimulatorPage() {
  const pack = usePack()
  const inr = pack.data?.currency === 'INR'
  const unit = inr ? 1e7 : 1e6
  const unitLabel = inr ? 'crore' : 'million'
  const [amount, setAmount] = useState('50')
  const [strategy, setStrategy] = useState<Strategy>('balanced')
  const run = useMutation({
    mutationFn: (body: { budget: number; strategy: Strategy }) => post<Simulation>('/api/v1/simulate', body),
  })

  const budget = Number(amount) * unit
  const submit = (next: Strategy = strategy) => {
    if (budget > 0) run.mutate({ budget, strategy: next })
  }
  const result = run.data
  const currency = pack.data?.currency ?? ''
  const symbol = pack.data?.currency_symbol ?? ''

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="Given a budget, which unserved gaps should be funded first? Places needing an audit are not funded here — more money is not the answer when existing money is not reaching people."
      />

      <Panel className="mb-6">
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <label className="block">
            <span className="mb-1 block text-[12px] text-muted">Budget ({symbol} {unitLabel})</span>
            <input
              className={`${inputStyle} num w-36`}
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))}
            />
          </label>
          <div>
            <span className="mb-1 block text-[12px] text-muted">Strategy</span>
            <Segmented
              label="Strategy"
              value={strategy}
              onChange={(value) => {
                setStrategy(value)
                if (result) submit(value)
              }}
              options={STRATEGIES.map((s) => ({ value: s.value, label: s.label }))}
            />
          </div>
          <Button variant="primary" type="submit" disabled={!(budget > 0) || run.isPending}>
            {run.isPending ? 'Calculating…' : 'Allocate'}
          </Button>
        </form>
        <p className="mt-3 text-[12px] text-faint">{STRATEGIES.find((s) => s.value === strategy)?.explain}</p>
      </Panel>

      {run.isError && <ErrorState error={run.error} />}
      {result &&
        (result.candidates === 0 ? (
          <EmptyState title="No fundable gaps with a cost estimate">
            Unserved gaps need an official statistic and a cost assumption in the country pack before they can be priced.
          </EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Places funded" value={`${formatNumber(result.funded.length)} of ${formatNumber(result.candidates)}`} />
              <Stat label="Estimated cost" value={formatMoney(result.total_cost, currency, symbol)} />
              <Stat label={`Unserved ${pack.data?.population_label ?? 'people'} reached`} value={formatNumber(result.beneficiaries)} />
              <Stat label="Sent for audit instead" value={formatNumber(result.audit_count)} hint="Delivery gaps and stalled money" to="/priorities?group=audit" />
            </div>

            <Panel title="Funded, in order" className="mt-6" flush>
              {result.funded.length === 0 ? (
                <p className="p-4 text-muted">The budget is smaller than the cheapest gap. Try a larger amount.</p>
              ) : (
                <table className="w-full text-left">
                  <thead className="text-[12px] text-faint">
                    <tr className="border-b border-line">
                      <th className="px-4 py-2 font-normal">Order</th>
                      <th className="px-2 py-2 font-normal">Place</th>
                      <th className="px-2 py-2 font-normal">Need</th>
                      <th className="px-2 py-2 text-right font-normal">Households</th>
                      <th className="px-4 py-2 text-right font-normal">Estimated cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.funded.map((f, i) => (
                      <tr key={f.priority_id} className="border-b border-line last:border-0">
                        <td className="num px-4 py-2 text-faint">{i + 1}</td>
                        <td className="px-2 py-2">
                          <Link to={`/priorities/${f.priority_id}`} className="font-medium hover:text-accent">{f.region_name}</Link>
                          <span className="ml-1.5 text-[12px] text-faint">rank {f.rank}</span>
                        </td>
                        <td className="px-2 py-2 text-muted">{needLabel(pack.data, f.sector)}</td>
                        <td className="num px-2 py-2 text-right">{formatNumber(f.beneficiaries)}</td>
                        <td className="num px-4 py-2 text-right">{formatMoney(f.cost, currency, symbol)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
            <ul className="mt-3 space-y-1 text-[12px] text-faint">
              {result.notes.map((note) => <li key={note}>{note}</li>)}
              <li>Unspent: {formatMoney(result.remaining, currency, symbol)}. Greedy allocation, so every step can be followed and checked.</li>
            </ul>
          </>
        ))}
    </>
  )
}
