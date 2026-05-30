// North indicator, parked at the plan's bottom-right corner.
export default function Compass({ x1, y1, fy, u }) {
  return (
    <g className="spln-compass" transform={`translate(${x1 - u * 1.2}, ${fy(y1) + u * 2.2})`}>
      <text textAnchor="middle" fontSize={u * 1.1} y={-u * 1.3}>N</text>
      <polygon points={`0,${-u} ${-u * 0.5},${u} 0,${u * 0.5} ${u * 0.5},${u}`} />
    </g>
  );
}
