import React from 'react';
import { AreaChart as RAC, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

const fmtAxis = (v) => v?.toLocaleString?.('en-IN', { maximumFractionDigits: 0 }) ?? v;

export const AreaChart = ({
  data, dataKey = 'price', xKey = 'date',
  color = '#F4C45D', height = 240, gradient = true,
  showGrid = false, showXAxis = true, showYAxis = false, areaOpacity = 0.25,
  formatter, baseline,
}) => {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RAC data={data} margin={{ top: 12, right: 8, bottom: 4, left: 0 }}>
        <defs>
          <linearGradient id={`area-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor={color} stopOpacity={areaOpacity} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        {showXAxis && (
          <XAxis
            dataKey={xKey}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
            tick={{ fontSize: 11, fill: '#64748B' }}
            tickFormatter={(v) => typeof v === 'string' ? v.slice(5) : v}
          />
        )}
        {showYAxis && (
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: '#64748B' }}
            width={48}
            tickFormatter={fmtAxis}
          />
        )}
        {typeof baseline === 'number' && (
          <ReferenceLine y={baseline} stroke="#384358" strokeDasharray="3 3" />
        )}
        <Tooltip
          cursor={{ stroke: '#384358', strokeWidth: 1, strokeDasharray: '3 3' }}
          contentStyle={{ background: '#171B25', border: '1px solid #262E40', borderRadius: 10, padding: '8px 10px' }}
          labelStyle={{ color: '#94A3B8', fontSize: 11, marginBottom: 4 }}
          itemStyle={{ color: '#F1F5F9', fontSize: 13, fontWeight: 600 }}
          formatter={formatter ?? ((v) => v?.toLocaleString?.('en-IN', { maximumFractionDigits: 2 }))}
        />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={1.75}
          fill={gradient ? `url(#area-${color})` : 'transparent'}
          isAnimationActive={true}
          animationDuration={500}
        />
      </RAC>
    </ResponsiveContainer>
  );
};
