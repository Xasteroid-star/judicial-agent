interface Dimension {
  label: string;
  value: number;
  weight: number;
}

interface Props {
  dimensions: Dimension[];
  finalConfidence: number;
  threshold: string;
}

const THRESHOLD_COLORS: Record<string, string> = {
  pass: "text-green-600 bg-green-50",
  review: "text-yellow-600 bg-yellow-50",
  uncertain: "text-orange-600 bg-orange-50",
  reject: "text-red-600 bg-red-50",
};

const THRESHOLD_LABELS: Record<string, string> = {
  pass: "通过",
  review: "需复核",
  uncertain: "存疑",
  reject: "驳回",
};

export function ConfidencePanel({ dimensions, finalConfidence, threshold }: Props) {
  const pct = Math.round(finalConfidence * 100);
  const colorClass = THRESHOLD_COLORS[threshold] || THRESHOLD_COLORS.review;

  return (
    <div className="bg-white rounded-lg border p-4">
      <h3 className="font-semibold text-gray-700 mb-4">置信度审查</h3>

      <div className="flex items-center gap-4 mb-4">
        <div className={`text-3xl font-bold ${colorClass.split(" ")[0]}`}>
          {pct}%
        </div>
        <span className={`px-2 py-1 rounded text-sm font-medium ${colorClass}`}>
          {THRESHOLD_LABELS[threshold] || threshold}
        </span>
      </div>

      <div className="w-full bg-gray-100 rounded-full h-2 mb-4">
        <div
          className="h-2 rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background:
              pct >= 85 ? "#16a34a" : pct >= 70 ? "#f59e0b" : pct >= 50 ? "#f97316" : "#dc2626",
          }}
        />
      </div>

      <div className="space-y-2">
        {dimensions.map((d) => (
          <div key={d.label} className="flex items-center justify-between text-sm">
            <span className="text-gray-500">
              {d.label} <span className="text-gray-300">×{d.weight}</span>
            </span>
            <div className="flex items-center gap-2">
              <div className="w-24 bg-gray-100 rounded-full h-1.5">
                <div
                  className="h-1.5 rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${Math.round(d.value * 100)}%` }}
                />
              </div>
              <span className="text-gray-700 w-8 text-right">
                {Math.round(d.value * 100)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
