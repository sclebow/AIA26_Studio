import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import * as api from "../api/client.js";

// Phase 6 — interactive Three.js 3D explore layer. Extrudes room floors + walls
// from the layout JSON, colors floors by comfort score, orbit to explore, click
// a room to select. Coordinate map: layout (x, y) -> three (x, z); up = y.
function scoreHex(v) {
  if (v == null) return 0x6a6a6a;
  return v < 0.5 ? 0xe8836a : v < 0.65 ? 0xd4b96a : 0x8bb88a;
}

export default function Layout3D({ rooms, selectedRoom, onSelect, layoutId }) {
  const mountRef = useRef(null);
  const [layout, setLayout] = useState(null);
  const [err, setErr] = useState("");
  const floorsRef = useRef({}); // roomName -> mesh

  useEffect(() => {
    let alive = true;
    api.getLayout()
      .then((d) => { if (alive) { setLayout(d.layout || null); if (!d.layout) setErr("no layout loaded yet"); } })
      .catch(() => { if (alive) setErr("could not load layout"); });
    return () => { alive = false; };
  }, [layoutId]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !layout) return;

    const W = mount.clientWidth || 360;
    const H = 340;
    const scoreByName = {};
    (rooms || []).forEach((r) => { scoreByName[r.roomName] = r.overallScore; });

    const scene = new THREE.Scene();
    scene.background = null;
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const dir = new THREE.DirectionalLight(0xffffff, 0.6);
    dir.position.set(8, 18, 6);
    scene.add(dir);

    // ── outline bounds → center + camera framing ──
    const outline = layout.outline || [];
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    outline.forEach(([x, y]) => { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y); });
    if (!isFinite(minX)) { minX = 0; maxX = 12; minY = 0; maxY = 8; }
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    const span = Math.max(maxX - minX, maxY - minY) || 12;

    const group = new THREE.Group();
    scene.add(group);
    const floors = {};

    // ── room floors (ShapeGeometry, colored by score) ──
    (layout.rooms || []).forEach((room) => {
      const geo = room.geometry || [];
      if (geo.length < 3) return;
      const shape = new THREE.Shape();
      geo.forEach(([x, y], i) => { if (i === 0) shape.moveTo(x - cx, y - cy); else shape.lineTo(x - cx, y - cy); });
      const g = new THREE.ShapeGeometry(shape);
      g.rotateX(-Math.PI / 2); // XY shape -> XZ floor plane
      const color = scoreHex(scoreByName[room.name]);
      const mat = new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(g, mat);
      mesh.position.y = 0.01;
      mesh.userData.room = room.name;
      group.add(mesh);
      floors[room.name] = mesh;
    });
    floorsRef.current = floors;

    // ── wall segments as thin boxes ──
    const wallH = 2.7;
    const addSeg = (p0, p1, color, h, thick) => {
      const dx = p1[0] - p0[0], dy = p1[1] - p0[1];
      const len = Math.hypot(dx, dy);
      if (len < 0.01) return;
      const box = new THREE.Mesh(
        new THREE.BoxGeometry(len, h, thick),
        new THREE.MeshStandardMaterial({ color })
      );
      box.position.set((p0[0] + p1[0]) / 2 - cx, h / 2, (p0[1] + p1[1]) / 2 - cy);
      box.rotation.y = -Math.atan2(dy, dx);
      group.add(box);
    };
    // outline walls
    for (let i = 0; i < outline.length - 1; i++) addSeg(outline[i], outline[i + 1], 0x2a2a2a, wallH, 0.12);
    // interior partitions
    (layout.structure || []).forEach((w) => { const g = w.geometry || []; if (g.length >= 2) addSeg(g[0], g[1], 0x2a2a2a, wallH, 0.1); });
    // windows (teal, lower + thinner)
    (layout.windows || []).forEach((wn) => { const g = wn.geometry || []; if (g.length >= 2) addSeg(g[0], g[1], 0x6ab8c8, 1.4, 0.14); });

    camera.position.set(span * 0.9, span * 1.0, span * 0.9);
    camera.lookAt(0, 0, 0);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0, 0);

    // ── click selection ──
    const ray = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const onClick = (e) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      ray.setFromCamera(mouse, camera);
      const hits = ray.intersectObjects(Object.values(floors));
      if (hits.length && onSelect) onSelect(hits[0].object.userData.room);
    };
    renderer.domElement.addEventListener("click", onClick);

    let raf;
    const animate = () => { raf = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); };
    animate();

    return () => {
      cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("click", onClick);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [layout, rooms, onSelect]);

  // highlight selected floor
  useEffect(() => {
    const floors = floorsRef.current;
    Object.entries(floors).forEach(([name, mesh]) => {
      mesh.material.opacity = name === selectedRoom ? 0.85 : 0.55;
    });
  }, [selectedRoom]);

  if (err) return <div className="ap-empty">{err}</div>;
  return <div ref={mountRef} style={{ width: "100%", height: 340 }} />;
}
