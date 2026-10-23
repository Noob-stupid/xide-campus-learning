/**
 * 习得 · 数据模型（与 Flask 后端 JSON 字段一一对应）。
 * 字段名必须和后端 jsonify 输出的 key 完全一致。
 */

export interface UserInfo {
  id: number;
  username?: string;
  name: string;
  role: string;
  college?: string;
  avatar?: string;
  cover?: string;
  signature?: string;
  interests?: string;
  avatar_url?: string;
  cover_url?: string;
  created_at?: string;
}

export interface FloorInfo {
  id: number;
  name: string;
  building: string;
  floor_no: number;
  plan_w: number;
  plan_h: number;
  seat_count?: number;
}

export interface BuildingInfo {
  id: number;
  name: string;
  code?: string;
  lat: number;
  lng: number;
  address?: string;
  description?: string;
}

export interface ReservationInfo {
  id: number;
  user_id: number;
  seat_id: number;
  subject: string;
  goal: string;
  start_at: string;
  end_at: string;
  status: string;
  seat_code?: string;
  zone?: string;
  user_name?: string;
}

export interface SeatInfo {
  id: number;
  floor_id: number;
  code: string;
  zone: string;
  x: number;
  y: number;
  w: number;
  h: number;
  status: string;
  features: string[];
  live_status: string;
  reservation?: ReservationInfo;
  mine?: boolean;
}

export interface StudySession {
  id: number;
  reservation_id: number;
  user_id: number;
  seat_id: number;
  subject: string;
  started_at: string;
  ended_at?: string;
  duration_min?: number;
  status: string;
  stuck_points?: string;
  seat_code?: string;
  zone?: string;
}

export interface ContentInfo {
  id: number;
  owner_id: number;
  title: string;
  subject: string;
  knowledge_point?: string;
  description?: string;
  source_type?: string;
  status: string;
  duration_sec?: number;
  cover_path?: string;
  file_path?: string;
  cover_url?: string;
  file_url?: string;
  owner_name?: string;
  views?: number;
  helpful?: number;
  unhelpful?: number;
}

export interface RelayPush {
  id: number;
  session_id: number;
  user_id: number;
  content_id: number;
  reason?: string;
  feedback?: string;
  opened_at?: string;
  created_at?: string;
  title?: string;
  subject?: string;
  knowledge_point?: string;
  duration_sec?: number;
  cover_path?: string;
  file_path?: string;
  cover_url?: string;
  file_url?: string;
  owner_name?: string;
  seat_code?: string;
}

export interface MessageInfo {
  id: number;
  user_id: number;
  kind: string;
  title: string;
  body: string;
  payload?: string;
  read: number;
  created_at: string;
}

export interface NavPathNode {
  code: string;
  x: number;
  y: number;
  kind?: string;
}

export interface StatsInfo {
  seats_total: number;
  seats_free: number;
  pending_review: number;
  contents_approved: number;
  sessions_today: number;
  pushes: number;
  helpful_rate: number;
}

/* ---------------- 响应信封 ---------------- */

export interface LoginResp {
  ok: boolean;
  error?: string;
  user?: UserInfo;
}

export interface MeResp {
  ok: boolean;
  error?: string;
  user?: UserInfo;
}

export interface FloorsResp {
  ok: boolean;
  error?: string;
  floors?: FloorInfo[];
}

export interface SeatsResp {
  ok: boolean;
  error?: string;
  seats?: SeatInfo[];
}

export interface BookingResp {
  ok: boolean;
  error?: string;
  reservation?: ReservationInfo;
}

export interface SessionResp {
  ok: boolean;
  error?: string;
  session?: StudySession;
}

export interface ReservationsResp {
  ok: boolean;
  error?: string;
  reservations?: ReservationInfo[];
}

export interface NavResp {
  ok: boolean;
  error?: string;
  path?: NavPathNode[];
  distance?: number;
  minutes?: number;
  steps?: string[];
  seat?: SeatInfo;
  floor?: FloorInfo;
}

export interface ContentsResp {
  ok: boolean;
  error?: string;
  contents?: ContentInfo[];
}

export interface PushesResp {
  ok: boolean;
  error?: string;
  pushes?: RelayPush[];
}

export interface MessagesResp {
  ok: boolean;
  error?: string;
  messages?: MessageInfo[];
}

export interface StatsResp {
  ok: boolean;
  error?: string;
  stats?: StatsInfo;
}

export interface TutorResp {
  ok: boolean;
  error?: string;
  tutor_id?: string;
  step?: number;
  question?: string;
  options?: string[];
  done?: boolean;
  explanation?: string;
  check_question?: string;
  resource?: ContentInfo;
  note?: string;
}

export interface AgentResp {
  ok: boolean;
  error?: string;
  intent?: string;
  agent?: string;
  reply?: string;
  suggestions?: string[];
}

export interface OutdoorResp {
  ok: boolean;
  error?: string;
  distance_m?: number;
  minutes?: number;
  bearing?: number;
  direction?: string;
  steps?: string[];
  amap_uri?: string;
  buildings?: BuildingInfo[];
  amap_configured?: boolean;
}

export interface ProfileResp {
  ok: boolean;
  error?: string;
  user?: UserInfo;
  stats?: Record<string, number>;
  sessions?: StudySession[];
  contents?: ContentInfo[];
  pushes?: RelayPush[];
}

export interface SimpleResp {
  ok: boolean;
  error?: string;
}