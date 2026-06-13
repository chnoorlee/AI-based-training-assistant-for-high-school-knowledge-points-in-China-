import React from 'react'
import Svg, { Polygon, Line, Circle, Text as SvgText } from 'react-native-svg'

// axes: [{ label, value(0~1) }]
export default function Radar({ axes = [], size = 280 }) {
  const cx = size / 2
  const r = size / 2 - 40
  const n = axes.length || 1
  const pt = (i, frac) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n
    return [cx + r * frac * Math.cos(ang), cx + r * frac * Math.sin(ang)]
  }
  const ring = (rr) => axes.map((_, i) => pt(i, rr).join(',')).join(' ')
  const dataPts = axes.map((a, i) => pt(i, Math.max(0.03, a.value)).join(',')).join(' ')

  return (
    <Svg width={size} height={size}>
      {[0.25, 0.5, 0.75, 1].map((rr, i) => (
        <Polygon key={i} points={ring(rr)} fill="none" stroke="#e5e7eb" strokeWidth="1" />
      ))}
      {axes.map((_, i) => {
        const [x, y] = pt(i, 1)
        return <Line key={i} x1={cx} y1={cx} x2={x} y2={y} stroke="#eef2f7" />
      })}
      <Polygon points={dataPts} fill="rgba(79,70,229,0.18)" stroke="#4f46e5" strokeWidth="2" />
      {axes.map((a, i) => {
        const [x, y] = pt(i, Math.max(0.03, a.value))
        return <Circle key={i} cx={x} cy={y} r="3" fill="#4f46e5" />
      })}
      {axes.map((a, i) => {
        const [x, y] = pt(i, 1.18)
        return (
          <SvgText key={i} x={x} y={y} fontSize="10" fill="#6b7280" textAnchor="middle">
            {a.label} {Math.round(a.value * 100)}%
          </SvgText>
        )
      })}
    </Svg>
  )
}
