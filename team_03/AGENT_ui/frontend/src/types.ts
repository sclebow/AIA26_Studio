export interface LayoutJSON {
  layoutId: string
  outline: [number, number][]
  rooms: RoomItem[]
  doors: DoorItem[]
  windows: WindowItem[]
  furniture: FurnitureItem[]
  mep: MEPItem[]
  structure: StructureItem[]
}

export interface RoomItem {
  id: string
  name: string
  geometry: [number, number][]
  attributes: { area: number; [key: string]: unknown }
}

export interface DoorItem {
  id: string
  type: string
  name: string
  geometry: [number, number][]
  attributes: { connectsRooms: string[]; [key: string]: unknown }
}

export interface WindowItem {
  id: string
  type: string
  name: string
  geometry: [number, number][]
  attributes: { roomId: string; [key: string]: unknown }
}

export interface FurnitureItem {
  id: string
  name: string
  geometry: [number, number][]
  attributes: { roomId?: string; height?: number; [key: string]: unknown }
}

export interface MEPItem {
  id: string
  name: string
  geometry: [number, number][]
  attributes: { system?: string; height?: number; [key: string]: unknown }
}

export interface StructureItem {
  id: string
  name: string
  geometry: [number, number][]
  attributes: { type?: string; material?: string; [key: string]: unknown }
}

export type LayerName = 'outline' | 'rooms' | 'doors' | 'windows' | 'furniture' | 'mep' | 'structure'

export interface LayerVisibility {
  outline: boolean
  rooms: boolean
  doors: boolean
  windows: boolean
  furniture: boolean
  mep: boolean
  structure: boolean
}
