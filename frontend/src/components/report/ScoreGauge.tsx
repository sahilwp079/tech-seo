"use client";
import { RadialBarChart, RadialBar, PolarAngleAxis } from "recharts";

interface Props {
  score: number | null;
}

export default function ScoreGauge({ score }: Props) {
  const value = score ?? 0;
  const color = value >= 80 ? "#22c55e" : value >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative flex items-center justify-center w-28 h-28">
      <RadialBarChart
        width={112}
        height={112}
        innerRadius={40}
        outerRadius={52}
        data={[{ value }]}
        startAngle={90}
        endAngle={90 - (value / 100) * 360}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
        <RadialBar dataKey="value" fill={color} background={{ fill: "#e5e7eb" }} />
      </RadialBarChart>
      <span className="absolute text-xl font-bold" style={{ color }}>
        {score ?? "—"}
      </span>
    </div>
  );
}
