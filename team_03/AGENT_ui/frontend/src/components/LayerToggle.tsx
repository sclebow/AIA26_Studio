import React from 'react'
import { useTheme } from './common/ThemeToggle'
import { LayerVisibility, LayerName } from '../types'

interface LayerToggleProps {
  layers: LayerVisibility
  onToggle: (layer: LayerName) => void
}

const LAYER_CONFIG: { key: LayerName; label: string; color: string }[] = [
  { key: 'outline',   label: 'Outline',   color: '#6B7B9E' },
  { key: 'rooms',     label: 'Rooms',     color: '#B5A898' },
  { key: 'structure', label: 'Walls',     color: '#8B8F96' },
  { key: 'doors',     label: 'Doors',     color: '#C4896E' },
  { key: 'windows',   label: 'Windows',   color: '#7A9DB8' },
  { key: 'furniture', label: 'Furniture', color: '#9888AD' },
  { key: 'mep',       label: 'MEP',       color: '#7EA68B' },
]

export default function LayerToggle({ layers, onToggle }: LayerToggleProps) {
  const { colors, theme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <div style={{
      padding: '8px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      fontSize: 12,
      color: colors.muted,
      userSelect: 'none',
    }}>
      {LAYER_CONFIG.map(({ key, label, color }) => (
        <label
          key={key}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            cursor: 'pointer',
            padding: '3px 0',
            opacity: layers[key] ? 1 : 0.4,
            transition: 'opacity 0.2s',
          }}
        >
          <input
            type="checkbox"
            checked={layers[key]}
            onChange={() => onToggle(key)}
            style={{ display: 'none' }}
          />
          <span style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: layers[key] ? color : (isDark ? '#333' : '#bbb'),
            border: `1px solid ${color}44`,
            transition: 'background 0.2s',
            flexShrink: 0,
            boxShadow: layers[key] ? `0 0 4px ${color}44` : 'none',
          }} />
          <span style={{
            color: layers[key] ? colors.text : colors.muted,
            transition: 'color 0.2s',
            fontSize: 11,
          }}>
            {label}
          </span>
        </label>
      ))}
    </div>
  )
}
