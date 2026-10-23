/**
 * 习得 · 全局主题常量（颜色 / 圆角 / 间距）。
 * 与 Web 端设计系统保持一致：深蓝主色 + 浅灰底。
 */
export class Theme {
  static readonly PRIMARY: string = '#0F2A4A';
  static readonly PRIMARY_LIGHT: string = '#1B4B7A';
  static readonly ACCENT: string = '#2F80ED';
  static readonly ACCENT_SOFT: string = '#E8F1FF';

  static readonly BG: string = '#F2F4F7';
  static readonly CARD: string = '#FFFFFF';
  static readonly TEXT: string = '#1A2233';
  static readonly TEXT_SUB: string = '#6B7785';
  static readonly TEXT_FAINT: string = '#9AA4B2';
  static readonly LINE: string = '#E4E8EF';
  static readonly WHITE: string = '#FFFFFF';

  // 座位状态色
  static readonly FREE: string = '#3FAE6B';
  static readonly BOOKED: string = '#E0A72E';
  static readonly USING: string = '#D9534F';
  static readonly MAINT: string = '#9CA3AF';

  static readonly DANGER: string = '#E5484D';
  static readonly SUCCESS: string = '#2E9E83';

  static readonly RADIUS: number = 14;
  static readonly RADIUS_SM: number = 10;
  static readonly PAD: number = 16;
}