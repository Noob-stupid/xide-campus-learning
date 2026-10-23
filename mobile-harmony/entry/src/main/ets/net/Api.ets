import { http } from '@kit.NetworkKit';
import { preferences } from '@kit.ArkData';
import { common } from '@kit.AbilityKit';
import { LoginResp, MeResp, FloorsResp, SeatsResp, BookingResp, SessionResp,
  ReservationsResp, NavResp, ContentsResp, PushesResp, MessagesResp, StatsResp,
  TutorResp, AgentResp, OutdoorResp, ProfileResp, SimpleResp } from '../model/Types';

/** TODO: 部署完成后改成你真实的 HTTPS 地址（必须 HTTPS，后端 Flask 走 session Cookie） */
export const BASE_URL: string = 'https://xide.example.com';

interface LoginBody {
  username: string;
  password: string;
}
interface BookBody {
  seat_id: number;
  subject: string;
  goal: string;
  start_at: string;
  end_at: string;
}
interface TextBody {
  text: string;
}
interface TutorStartBody {
  topic: string;
}
interface TutorAnswerBody {
  tutor_id: string;
  text: string;
}
interface FeedbackBody {
  value: string;
}
interface ProfileUpdateBody {
  name: string;
  college: string;
  signature: string;
  interests: string;
}

/**
 * 习得 API 客户端。
 * - 统一 session Cookie 管理（登录后持久化到首选项，重启 App 仍在线）
 * - 所有方法返回解析后的强类型响应
 */
export class Api {
  private static cookie: string = '';
  private static store: preferences.Preferences | undefined = undefined;

  static async init(ctx: common.Context): Promise<void> {
    try {
      Api.store = await preferences.getPreferences(ctx, 'xide_store');
      const c = await Api.store.get('cookie', '');
      if (typeof c === 'string') {
        Api.cookie = c as string;
      }
    } catch (e) {
      Api.cookie = '';
    }
  }

  static hasCookie(): boolean {
    return Api.cookie.length > 0;
  }

  static async clearSession(): Promise<void> {
    Api.cookie = '';
    if (Api.store) {
      try {
        await Api.store.delete('cookie');
        await Api.store.flush();
      } catch (e) {
      }
    }
  }

  private static captureCookie(resp: http.HttpResponse): void {
    const hdrs = resp.header as Record<string, Object>;
    if (!hdrs) {
      return;
    }
    const keys: string[] = Object.keys(hdrs);
    for (let i = 0; i < keys.length; i++) {
      const k: string = keys[i];
      if (k.toLowerCase() !== 'set-cookie') {
        continue;
      }
      const raw: Object = hdrs[k];
      let text: string = '';
      if (typeof raw === 'string') {
        text = raw as string;
      } else {
        text = JSON.stringify(raw);
      }
      const m: RegExpMatchArray | null = text.match(/session=[^;,\]]+/);
      if (m && m.length > 0) {
        Api.cookie = m[0];
        if (Api.store) {
          Api.store.putSync('cookie', Api.cookie);
          Api.store.flush();
        }
      }
    }
  }

  private static header(): Record<string, string> {
    const h: Record<string, string> = {};
    h['Content-Type'] = 'application/json';
    h['Accept'] = 'application/json';
    if (Api.cookie.length > 0) {
      h['Cookie'] = Api.cookie;
    }
    return h;
  }

  private static async call(method: http.RequestMethod, path: string, body?: Object): Promise<string> {
    const req: http.HttpRequest = http.createHttp();
    const opts: http.HttpRequestOptions = {
      method: method,
      header: Api.header(),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 15000,
      readTimeout: 15000
    };
    if (body !== undefined) {
      opts.extraData = JSON.stringify(body);
    }
    try {
      const resp: http.HttpResponse = await req.request(BASE_URL + path, opts);
      Api.captureCookie(resp);
      const r: Object | string | ArrayBuffer = resp.result;
      if (typeof r === 'string') {
        return r as string;
      }
      return JSON.stringify(r);
    } finally {
      req.destroy();
    }
  }

  // ---------------- 认证 ----------------
  static async login(username: string, password: string): Promise<LoginResp> {
    const body: LoginBody = { username: username, password: password };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/auth/login', body);
    return JSON.parse(text) as LoginResp;
  }

  static async logout(): Promise<SimpleResp> {
    const text: string = await Api.call(http.RequestMethod.POST, '/api/auth/logout');
    return JSON.parse(text) as SimpleResp;
  }

  static async me(): Promise<MeResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/me');
    return JSON.parse(text) as MeResp;
  }

  // ---------------- 空间 / 预约 ----------------
  static async floors(): Promise<FloorsResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/floors');
    return JSON.parse(text) as FloorsResp;
  }

  static async seats(floorId: number): Promise<SeatsResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/seats?floor_id=' + floorId.toString());
    return JSON.parse(text) as SeatsResp;
  }

  static async book(seatId: number, subject: string, goal: string, startAt: string, endAt: string): Promise<BookingResp> {
    const body: BookBody = { seat_id: seatId, subject: subject, goal: goal, start_at: startAt, end_at: endAt };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/bookings', body);
    return JSON.parse(text) as BookingResp;
  }

  static async checkin(rid: number): Promise<SessionResp> {
    const text: string = await Api.call(http.RequestMethod.POST, '/api/bookings/' + rid.toString() + '/checkin');
    return JSON.parse(text) as SessionResp;
  }

  static async endBooking(rid: number): Promise<SessionResp> {
    const text: string = await Api.call(http.RequestMethod.POST, '/api/bookings/' + rid.toString() + '/end');
    return JSON.parse(text) as SessionResp;
  }

  static async currentSession(): Promise<SessionResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/sessions/current');
    return JSON.parse(text) as SessionResp;
  }

  static async myReservations(): Promise<ReservationsResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/my/reservations');
    return JSON.parse(text) as ReservationsResp;
  }

  static async nav(seatId: number, from: string): Promise<NavResp> {
    const text: string = await Api.call(http.RequestMethod.GET,
      '/api/nav?seat_id=' + seatId.toString() + '&from=' + encodeURIComponent(from));
    return JSON.parse(text) as NavResp;
  }

  // ---------------- 学习 / 辅导 ----------------
  static async tutorStart(topic: string): Promise<TutorResp> {
    const body: TutorStartBody = { topic: topic };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/tutor/start', body);
    return JSON.parse(text) as TutorResp;
  }

  static async tutorAnswer(tutorId: string, answer: string): Promise<TutorResp> {
    const body: TutorAnswerBody = { tutor_id: tutorId, text: answer };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/tutor/answer', body);
    return JSON.parse(text) as TutorResp;
  }

  static async agentAsk(text0: string): Promise<AgentResp> {
    const body: TextBody = { text: text0 };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/agent/ask', body);
    return JSON.parse(text) as AgentResp;
  }

  // ---------------- 内容 / 接棒 / 消息 ----------------
  static async contents(status: string, subject: string): Promise<ContentsResp> {
    let q: string = '/api/contents?status=' + encodeURIComponent(status);
    if (subject.length > 0) {
      q = q + '&subject=' + encodeURIComponent(subject);
    }
    const text: string = await Api.call(http.RequestMethod.GET, q);
    return JSON.parse(text) as ContentsResp;
  }

  static async relayPending(): Promise<PushesResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/relay/pending');
    return JSON.parse(text) as PushesResp;
  }

  static async relayOpen(pid: number): Promise<SimpleResp> {
    const text: string = await Api.call(http.RequestMethod.POST, '/api/relay/' + pid.toString() + '/open');
    return JSON.parse(text) as SimpleResp;
  }

  static async relayFeedback(pid: number, value: string): Promise<SimpleResp> {
    const body: FeedbackBody = { value: value };
    const text: string = await Api.call(http.RequestMethod.POST,
      '/api/relay/' + pid.toString() + '/feedback', body);
    return JSON.parse(text) as SimpleResp;
  }

  static async messages(): Promise<MessagesResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/messages');
    return JSON.parse(text) as MessagesResp;
  }

  static async messagesRead(id: number): Promise<SimpleResp> {
    const body: TextBody = { text: id.toString() };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/messages/read', body);
    return JSON.parse(text) as SimpleResp;
  }

  // ---------------- 我的 ----------------
  static async profile(): Promise<ProfileResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/profile');
    return JSON.parse(text) as ProfileResp;
  }

  static async profileUpdate(name: string, college: string, signature: string, interests: string): Promise<SimpleResp> {
    const body: ProfileUpdateBody = { name: name, college: college, signature: signature, interests: interests };
    const text: string = await Api.call(http.RequestMethod.POST, '/api/profile/update', body);
    return JSON.parse(text) as SimpleResp;
  }

  // ---------------- 室外 / 统计 ----------------
  static async outdoor(building: string, lat?: number, lng?: number): Promise<OutdoorResp> {
    let path: string = '/api/outdoor?building=' + encodeURIComponent(building);
    if (lat !== undefined && lng !== undefined) {
      path += '&lat=' + lat.toString() + '&lng=' + lng.toString();
    }
    const text: string = await Api.call(http.RequestMethod.GET, path);
    return JSON.parse(text) as OutdoorResp;
  }

  static async stats(): Promise<StatsResp> {
    const text: string = await Api.call(http.RequestMethod.GET, '/api/stats');
    return JSON.parse(text) as StatsResp;
  }

  static async demoExpire(): Promise<SimpleResp> {
    const text: string = await Api.call(http.RequestMethod.POST, '/api/demo/expire');
    return JSON.parse(text) as SimpleResp;
  }
}