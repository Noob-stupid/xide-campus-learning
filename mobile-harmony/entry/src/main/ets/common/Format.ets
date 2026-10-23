/**
 * 习得 · 通用格式化 / 时间工具。
 */
export class Fmt {
  static pad2(n: number): string {
    return n < 10 ? '0' + n.toString() : n.toString();
  }

  /** 解析后端时间字符串 "YYYY-MM-DD HH:MM:SS" */
  static parse(s?: string): Date | undefined {
    if (!s || s.length === 0) {
      return undefined;
    }
    const t: string = s.replace(/-/g, '/');
    const d = new Date(t);
    if (isNaN(d.getTime())) {
      return undefined;
    }
    return d;
  }

  /** 现在 → 秒（非负） */
  static nowStamp(): string {
    const d = new Date();
    return Fmt.dateStr(d) + ' ' + Fmt.pad2(d.getHours()) + ':' + Fmt.pad2(d.getMinutes()) + ':' + Fmt.pad2(d.getSeconds());
  }

  private static dateStr(d: Date): string {
    return d.getFullYear() + '-' + Fmt.pad2(d.getMonth() + 1) + '-' + Fmt.pad2(d.getDate());
  }

  /** 从 started_at 到现在已过的秒数 */
  static elapsedSec(startedAt?: string): number {
    const d = Fmt.parse(startedAt);
    if (!d) {
      return 0;
    }
    const diff: number = Math.floor((Date.now() - d.getTime()) / 1000);
    return diff > 0 ? diff : 0;
  }

  /** 秒 → HH:MM:SS */
  static clock(sec: number): string {
    const h: number = Math.floor(sec / 3600);
    const m: number = Math.floor((sec % 3600) / 60);
    const s: number = sec % 60;
    return Fmt.pad2(h) + ':' + Fmt.pad2(m) + ':' + Fmt.pad2(s);
  }

  /** 秒 → "N 分钟" */
  static durationText(sec?: number): string {
    if (!sec || sec <= 0) {
      return '--';
    }
    const m: number = Math.round(sec / 60);
    if (m < 1) {
      return '1 分钟内';
    }
    return m.toString() + ' 分钟';
  }

  static minutesText(min?: number): string {
    if (!min || min <= 0) {
      return '0 分钟';
    }
    return min.toString() + ' 分钟';
  }

  static greeting(name: string): string {
    const h: number = new Date().getHours();
    let g: string = '你好';
    if (h < 6) {
      g = '凌晨好';
    } else if (h < 12) {
      g = '上午好';
    } else if (h < 14) {
      g = '中午好';
    } else if (h < 18) {
      g = '下午好';
    } else {
      g = '晚上好';
    }
    return g + '，' + name;
  }

  static hhmm(s?: string): string {
    const d = Fmt.parse(s);
    if (!d) {
      return '--';
    }
    return Fmt.pad2(d.getHours()) + ':' + Fmt.pad2(d.getMinutes());
  }

  static channelText(s?: string): string {
    const d = Fmt.parse(s);
    if (!d) {
      return '--';
    }
    return (d.getMonth() + 1).toString() + '月' + d.getDate().toString() + '日 ' + Fmt.hhmm(s);
  }

  /** 座位实时状态 → 中文 */
  static seatStatusText(s: string): string {
    if (s === 'free') {
      return '空闲';
    }
    if (s === 'booked') {
      return '已预约';
    }
    if (s === 'using') {
      return '使用中';
    }
    if (s === 'maintenance') {
      return '维护中';
    }
    return '未知';
  }

  /** 预约状态 → 中文 */
  static reservationStatusText(s: string): string {
    if (s === 'booked') {
      return '已预约';
    }
    if (s === 'checked_in') {
      return '学习中';
    }
    if (s === 'completed') {
      return '已完成';
    }
    if (s === 'cancelled') {
      return '已取消';
    }
    if (s === 'expired') {
      return '已过期';
    }
    if (s === 'no_show') {
      return '未到场';
    }
    return s;
  }

  /** 座位特征 → 中文 */
  static featureText(f: string): string {
    if (f === 'window') {
      return '靠窗';
    }
    if (f === 'quiet') {
      return '安静';
    }
    if (f === 'power') {
      return '电源';
    }
    if (f === 'group') {
      return '可讨论';
    }
    return f;
  }
}