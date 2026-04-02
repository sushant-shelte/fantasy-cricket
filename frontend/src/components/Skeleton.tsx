/** Reusable skeleton shimmer primitives */

export function SkeletonPulse({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-white/10 ${className}`} />;
}

/** Dashboard match card skeleton */
export function MatchCardSkeleton() {
  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <SkeletonPulse className="h-6 w-20" />
        <SkeletonPulse className="h-4 w-12" />
      </div>
      <SkeletonPulse className="h-3 w-16 mx-auto" />
      <div className="flex items-center justify-center gap-3">
        <SkeletonPulse className="h-7 w-24" />
        <SkeletonPulse className="h-6 w-8 rounded-lg" />
        <SkeletonPulse className="h-7 w-24" />
      </div>
      <SkeletonPulse className="h-3 w-32 mx-auto" />
      <div className="flex justify-center">
        <SkeletonPulse className="h-10 w-32 rounded-xl" />
      </div>
    </div>
  );
}

/** Dashboard skeleton: hero + tabs + cards */
export function DashboardSkeleton() {
  return (
    <div className="-mx-4 -mt-6">
      {/* Hero shimmer */}
      <div className="relative overflow-hidden rounded-b-3xl mb-6">
        <SkeletonPulse className="h-48 w-full rounded-none" />
      </div>
      <div className="px-4 space-y-6">
        {/* Tabs */}
        <div className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
          <SkeletonPulse className="flex-1 h-9 rounded-lg" />
          <SkeletonPulse className="flex-1 h-9 rounded-lg" />
          <SkeletonPulse className="flex-1 h-9 rounded-lg" />
        </div>
        {/* Cards */}
        <div className="grid gap-3 sm:grid-cols-2">
          <MatchCardSkeleton />
          <MatchCardSkeleton />
          <MatchCardSkeleton />
          <MatchCardSkeleton />
        </div>
      </div>
    </div>
  );
}

/** Player list skeleton for SelectTeam */
export function PlayerListSkeleton() {
  return (
    <div className="space-y-1">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <SkeletonPulse className="w-6 h-6 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <SkeletonPulse className="h-4 w-10 rounded-full" />
              <SkeletonPulse className="h-4 w-28" />
            </div>
            <SkeletonPulse className="h-3 w-16" />
          </div>
          <SkeletonPulse className="w-7 h-7 rounded-full" />
          <SkeletonPulse className="w-7 h-7 rounded-full" />
        </div>
      ))}
    </div>
  );
}

/** Score page skeleton */
export function ScoresSkeleton() {
  return (
    <div className="space-y-4">
      {/* Contestant rankings */}
      <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10">
          <SkeletonPulse className="h-5 w-40" />
        </div>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-white/5 last:border-0">
            <SkeletonPulse className="w-8 h-6 rounded" />
            <SkeletonPulse className="h-4 w-24 flex-1" />
            <SkeletonPulse className="h-4 w-16" />
          </div>
        ))}
      </div>
      {/* Player stats */}
      <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10">
          <SkeletonPulse className="h-5 w-36" />
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-white/5 last:border-0">
            <SkeletonPulse className="h-4 w-8 rounded-full" />
            <SkeletonPulse className="h-4 w-32 flex-1" />
            <SkeletonPulse className="h-4 w-20" />
            <SkeletonPulse className="h-4 w-12" />
          </div>
        ))}
      </div>
    </div>
  );
}
