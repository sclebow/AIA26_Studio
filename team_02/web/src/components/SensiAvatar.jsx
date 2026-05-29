// The concentric six-sense ring mark, reused as the brand avatar everywhere.
// `static` renders the demoted small dot used for previous messages in a thread.

export default function SensiAvatar({ size = 28, className = "sensi-avatar", animate = true }) {
  const rings = [
    { r: 14.5, stroke: "#E8836A", delay: "0s" },
    { r: 12, stroke: "#D4B96A", delay: ".5s" },
    { r: 9.5, stroke: "#9B8FD4", delay: "1s" },
    { r: 7, stroke: "#6AB8C8", delay: "1.5s" },
    { r: 4.5, stroke: "#8BB88A", delay: "2s" },
    { r: 2, stroke: "#C4A882", delay: "2.5s" },
  ];
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 32 32" fill="none">
      {rings.map((ring, i) => (
        <circle
          key={i}
          cx="16"
          cy="16"
          r={ring.r}
          stroke={ring.stroke}
          strokeWidth=".8"
          style={animate ? { animation: `srg${i} 3s ease-in-out infinite`, animationDelay: ring.delay } : undefined}
        />
      ))}
      <circle cx="16" cy="16" r="1.2" fill="#F0EDE8" opacity=".80" />
    </svg>
  );
}
