"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { monthLabel, shortDate } from "@/lib/format";
import type { ChartSpec, ForecastPoint } from "@/lib/types";
import { useMoney } from "./UserContext";

const SKY = "#0099FF";
const SERIES_TWO = "#1A5A8A";
const EMBER = "#E5533D";
const GRID = "#D3E7F5";
const AXIS = "#4A6678";
const axisTick = { fill: AXIS, fontSize: 12 };

type TipRow = { label: string; value: string };

function TipBox({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="tooltip">
      <b>{title}</b>
      {rows.map((row) => (
        <div key={row.label}>
          {row.label}: {row.value}
        </div>
      ))}
    </div>
  );
}

function compact(cents: number): string {
  const dollars = cents / 100;
  if (Math.abs(dollars) >= 1000) return `${(dollars / 1000).toFixed(Math.abs(dollars) >= 10000 ? 0 : 1)}k`;
  return `${Math.round(dollars)}`;
}

export function HBars({ rows }: { rows: { label: string; value_cents: number }[] }) {
  const money = useMoney();
  const max = Math.max(...rows.map((row) => row.value_cents), 1);
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <div className="bar-labels">
            <span>{row.label}</span>
            <strong>{money(row.value_cents, true)}</strong>
          </div>
          <div className="bar-track" aria-hidden="true">
            <div className="bar-fill" style={{ width: `${Math.max((row.value_cents / max) * 100, 1)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** The signature chart: cloud-white balance rising into the sky band, with the low point marked. */
export function Horizon({ points, low }: { points: ForecastPoint[]; low: { date: string; balance_cents: number } | null }) {
  const money = useMoney();
  const values = points.map((p) => p.balance_cents);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max((max - min) * 0.25, 5000);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 30, right: 0, bottom: 0, left: 0 }}>
        <XAxis dataKey="date" hide />
        <YAxis domain={[min - pad, max + pad]} hide />
        <Tooltip
          cursor={{ stroke: "#06283D", strokeWidth: 1 }}
          content={({ active, payload }: any) =>
            active && payload?.[0] ? (
              <TipBox
                title={shortDate(payload[0].payload.date)}
                rows={[
                  { label: "Expected", value: money(payload[0].payload.balance_cents, true) },
                  {
                    label: "Likely range",
                    value: `${money(payload[0].payload.low_cents, true)} to ${money(payload[0].payload.high_cents, true)}`,
                  },
                ]}
              />
            ) : null
          }
        />
        <Area
          dataKey="balance_cents"
          type="monotone"
          stroke="#FDFDFE"
          strokeWidth={2}
          fill="#FDFDFE"
          fillOpacity={1}
          baseValue={min - pad}
          isAnimationActive={false}
          activeDot={{ r: 5, fill: "#06283D", stroke: "#FDFDFE", strokeWidth: 2 }}
        />
        {low && <ReferenceDot x={low.date} y={low.balance_cents} r={7} fill={EMBER} stroke="#FDFDFE" strokeWidth={2} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ForecastChart({ points, height = 240 }: { points: ForecastPoint[]; height?: number }) {
  const money = useMoney();
  const rows = points.map((p) => ({ ...p, band: [p.low_cents, p.high_cents] as [number, number] }));
  const low = points.length ? points.slice(1).reduce((a, b) => (b.balance_cents < a.balance_cents ? b : a), points[0]) : null;
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="date" tickFormatter={shortDate} tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={48} />
          <YAxis tickFormatter={compact} tick={axisTick} tickLine={false} axisLine={false} width={44} />
          <Tooltip
            content={({ active, payload }: any) =>
              active && payload?.[0] ? (
                <TipBox
                  title={shortDate(payload[0].payload.date)}
                  rows={[
                    { label: "Expected", value: money(payload[0].payload.balance_cents, true) },
                    {
                      label: "Likely range",
                      value: `${money(payload[0].payload.low_cents, true)} to ${money(payload[0].payload.high_cents, true)}`,
                    },
                  ]}
                />
              ) : null
            }
          />
          <Area dataKey="band" stroke="none" fill={SKY} fillOpacity={0.14} isAnimationActive={false} activeDot={false} />
          <Line dataKey="balance_cents" stroke={SKY} strokeWidth={2} dot={false} isAnimationActive={false} activeDot={{ r: 5, stroke: "#FDFDFE", strokeWidth: 2 }} />
          {low && <ReferenceDot x={low.date} y={low.balance_cents} r={6} fill={EMBER} stroke="#FDFDFE" strokeWidth={2} />}
          <ReferenceLine y={0} stroke={AXIS} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CashflowChart({ rows, height = 240 }: { rows: { label: string; income_cents: number; spending_cents: number }[]; height?: number }) {
  const money = useMoney();
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="legend">
        <span>
          <i style={{ background: SERIES_TWO }} />
          Income
        </span>
        <span>
          <i style={{ background: SKY }} />
          Spending
        </span>
      </div>
      <div className="chart-box" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} barGap={2} barCategoryGap="28%">
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tickFormatter={monthLabel} tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} />
            <YAxis tickFormatter={compact} tick={axisTick} tickLine={false} axisLine={false} width={40} />
            <Tooltip
              cursor={{ fill: "#E8F5FF" }}
              content={({ active, payload }: any) =>
                active && payload?.[0] ? (
                  <TipBox
                    title={monthLabel(payload[0].payload.label)}
                    rows={[
                      { label: "Income", value: money(payload[0].payload.income_cents, true) },
                      { label: "Spending", value: money(payload[0].payload.spending_cents, true) },
                      { label: "Left over", value: money(payload[0].payload.income_cents - payload[0].payload.spending_cents, true) },
                    ]}
                  />
                ) : null
              }
            />
            <Bar dataKey="income_cents" fill={SERIES_TWO} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="spending_cents" fill={SKY} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function ScenarioChart({ rows, height = 220 }: { rows: { label: string; baseline_cents: number; scenario_cents: number }[]; height?: number }) {
  const money = useMoney();
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="legend">
        <span>
          <i style={{ background: SERIES_TWO }} />
          Now
        </span>
        <span>
          <i style={{ background: SKY }} />
          With this change
        </span>
      </div>
      <div className="chart-box" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tickFormatter={monthLabel} tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
            <YAxis tickFormatter={compact} tick={axisTick} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              content={({ active, payload }: any) =>
                active && payload?.[0] ? (
                  <TipBox
                    title={monthLabel(payload[0].payload.label)}
                    rows={[
                      { label: "Now", value: money(payload[0].payload.baseline_cents, true) },
                      { label: "With this change", value: money(payload[0].payload.scenario_cents, true) },
                    ]}
                  />
                ) : null
              }
            />
            <Line dataKey="baseline_cents" stroke={SERIES_TWO} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line dataKey="scenario_cents" stroke={SKY} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function ChatChart({ spec }: { spec: ChartSpec }) {
  const money = useMoney();
  let body: React.ReactNode = null;
  if (spec.kind === "bars") body = <HBars rows={spec.rows} />;
  if (spec.kind === "forecast") body = <ForecastChart points={spec.rows} height={190} />;
  if (spec.kind === "cashflow") body = <CashflowChart rows={spec.rows} height={180} />;
  if (spec.kind === "scenario") body = <ScenarioChart rows={spec.rows} height={190} />;
  if (spec.kind === "budget") {
    body = (
      <div className="bars">
        {spec.rows.map((row) => (
          <div className="bar-row" key={row.label}>
            <div className="bar-labels">
              <span>{row.label}</span>
              <span>
                {money(row.spent_cents, true)} of {money(row.limit_cents, true)}
              </span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <div className={`bar-fill ${row.status === "over" ? "over" : ""}`} style={{ width: `${Math.min((row.spent_cents / Math.max(row.limit_cents, 1)) * 100, 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (spec.kind === "goals") {
    body = (
      <div className="bars">
        {spec.rows.map((row) => (
          <div className="bar-row" key={row.label}>
            <div className="bar-labels">
              <span>{row.label}</span>
              <span>
                {money(row.saved_cents, true)} of {money(row.target_cents, true)}
              </span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <div className="bar-fill" style={{ width: `${Math.min((row.saved_cents / Math.max(row.target_cents, 1)) * 100, 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <figure className="reply-chart" style={{ margin: 0 }}>
      <figcaption>
        <h3>{spec.title}</h3>
      </figcaption>
      {body}
    </figure>
  );
}
