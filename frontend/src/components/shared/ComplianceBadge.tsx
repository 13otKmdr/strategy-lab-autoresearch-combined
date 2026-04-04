import { ShieldCheck, ShieldAlert } from 'lucide-react'

export default function ComplianceBadge({ status }: { status: string }) {
  if (status === 'compliant') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md bg-accent-green/15 text-accent-green border border-accent-green/30">
        <ShieldCheck className="w-3.5 h-3.5" />
        Compliant
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md bg-accent-red/15 text-accent-red border border-accent-red/30">
      <ShieldAlert className="w-3.5 h-3.5" />
      Non-Compliant
    </span>
  )
}
