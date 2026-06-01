import SensiAvatar from "../components/SensiAvatar.jsx";

// Shared top-bar shell — the brand pill (avatar + "sensi") was repeated in all
// five screens. TopBar renders that shell; each screen passes its own trailing
// content (step pill, layout picker + status group, section label) as children.
export default function TopBar({ wide = false, children }) {
  return (
    <div className="top-bar">
      <div className={"top-bar-pill" + (wide ? " top-bar-pill--wide" : "")}>
        <SensiAvatar size={26} />
        <span className="top-bar-label">sensi</span>
        {children}
      </div>
    </div>
  );
}
