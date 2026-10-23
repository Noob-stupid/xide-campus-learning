import { Api } from '../net/Api';
import { Theme } from '../common/Theme';
import { Fmt } from '../common/Format';
import { StatsInfo, StudySession, RelayPush, UserInfo } from '../model/Types';
import { router } from '@kit.ArkUI';

/** 今日页：问候、数据卡、当前场次、今日建议、最近接棒 */
@Component
export struct HomeView {
  @State stats: StatsInfo | null = null;
  @State session: StudySession | null = null;
  @State pushes: RelayPush[] = [];
  @State user: UserInfo | null = null;
  @State loading: boolean = true;
  @State err: string = '';
  @State tick: number = 0;
  private timer: number = -1;

  aboutToAppear(): void {
    const u = AppStorage.get<UserInfo>('user');
    if (u) {
      this.user = u;
    }
    this.load();
    this.timer = setInterval(() => {
      if (this.session) {
        this.tick = this.tick + 1;
      }
    }, 1000);
  }

  aboutToDisappear(): void {
    if (this.timer >= 0) {
      clearInterval(this.timer);
      this.timer = -1;
    }
  }

  async load(): Promise<void> {
    this.loading = true;
    this.err = '';
    try {
      const s = await Api.stats();
      if (s.ok && s.stats) {
        this.stats = s.stats;
      }
      const cs = await Api.currentSession();
      if (cs.ok) {
        this.session = cs.session ?? null;
      }
      const p = await Api.relayPending();
      if (p.ok && p.pushes) {
        this.pushes = p.pushes;
      }
    } catch (e) {
      this.err = '加载失败，请检查网络后重试';
    } finally {
      this.loading = false;
    }
  }

  roleText(): string {
    const r = this.user ? this.user.role : 'student';
    if (r === 'student') {
      return '学生';
    }
    if (r === 'teacher') {
      return '教师';
    }
    if (r === 'reviewer') {
      return '审核员';
    }
    if (r === 'admin') {
      return '管理员';
    }
    return r;
  }

  @Builder
  statCard(label: string, value: string, color: string) {
    Column({ space: 4 }) {
      Text(value)
        .fontSize(22)
        .fontWeight(FontWeight.Bold)
        .fontColor(color)
      Text(label)
        .fontSize(12)
        .fontColor(Theme.TEXT_SUB)
    }
    .layoutWeight(1)
    .padding(14)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  suggestion(icon: string, title: string, body: string) {
    Row({ space: 10 }) {
      Text(icon)
        .fontSize(20)
      Column({ space: 3 }) {
        Text(title)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
        Text(body)
          .fontSize(12)
          .fontColor(Theme.TEXT_SUB)
      }
      .alignItems(HorizontalAlign.Start)
      .layoutWeight(1)
    }
    .width('100%')
    .padding(12)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS_SM)
  }

  @Builder
  sessionCard(s: StudySession) {
    Column({ space: 10 }) {
      Row() {
        Text('当前学习')
          .fontSize(13)
          .fontColor(Theme.TEXT_SUB)
        Blank()
        Text(s.seat_code ? s.seat_code : '')
          .fontSize(13)
          .fontColor(Theme.ACCENT)
      }
      .width('100%')

      Text(Fmt.clock(Fmt.elapsedSec(s.started_at)))
        .fontSize(34)
        .fontWeight(FontWeight.Bold)
        .fontColor(Theme.PRIMARY)

      Text((s.subject ? s.subject : '自主学习') + ' · ' + (s.zone ? s.zone : ''))
        .fontSize(12)
        .fontColor(Theme.TEXT_SUB)

      Row({ space: 10 }) {
        Button('进入学习')
          .layoutWeight(1)
          .height(42)
          .backgroundColor(Theme.PRIMARY)
          .fontColor(Theme.WHITE)
          .onClick(() => {
            AppStorage.setOrCreate('tab', 2);
          })
        Button('结束学习')
          .layoutWeight(1)
          .height(42)
          .backgroundColor('#FBE9EA')
          .fontColor(Theme.DANGER)
          .onClick(() => {
            this.endSession(s);
          })
      }
      .width('100%')
    }
    .width('100%')
    .padding(16)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(HorizontalAlign.Start)
  }

  async endSession(s: StudySession): Promise<void> {
    try {
      const r = await Api.endBooking(s.reservation_id);
      if (r.ok) {
        this.session = null;
        await this.load();
      }
    } catch (e) {
    }
  }

  build() {
    Scroll() {
      Column({ space: 14 }) {
        // 问候头
        Column({ space: 5 }) {
          Text(Fmt.greeting(this.user ? this.user.name : '同学'))
            .fontSize(21)
            .fontWeight(FontWeight.Bold)
            .fontColor(Theme.WHITE)
          Text(this.roleText() + ' · ' + Fmt.channelText(Fmt.nowStamp()))
            .fontSize(12)
            .fontColor('#B9C7DB')
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
        .padding(18)
        .backgroundColor(Theme.PRIMARY)
        .borderRadius(Theme.RADIUS)

        if (this.err.length > 0) {
          Row() {
            Text(this.err)
              .fontSize(13)
              .fontColor(Theme.DANGER)
            Blank()
            Text('重试')
              .fontSize(13)
              .fontColor(Theme.ACCENT)
              .onClick(() => {
                this.load();
              })
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#FDF1F1')
          .borderRadius(Theme.RADIUS_SM)
        }

        // 数据卡
        Row({ space: 12 }) {
          this.statCard('空闲座位', this.stats ? this.stats.seats_free.toString() : '-', Theme.FREE)
          this.statCard('今日场次', this.stats ? this.stats.sessions_today.toString() : '-', Theme.ACCENT)
        }
        .width('100%')

        Row({ space: 12 }) {
          this.statCard('接棒总数', this.stats ? this.stats.pushes.toString() : '-', Theme.BOOKED)
          this.statCard('有帮助率', this.stats ? this.stats.helpful_rate.toString() + '%' : '-', Theme.SUCCESS)
        }
        .width('100%')

        // 当前场次
        if (this.session) {
          this.sessionCard(this.session as StudySession)
        } else {
          Column({ space: 10 }) {
            Text('当前没有进行中的学习')
              .fontSize(14)
              .fontColor(Theme.TEXT_SUB)
            Button('去找一个座位')
              .width('100%')
              .height(42)
              .backgroundColor(Theme.PRIMARY)
              .fontColor(Theme.WHITE)
              .onClick(() => {
                AppStorage.setOrCreate('tab', 1);
              })
          }
          .width('100%')
          .padding(16)
          .backgroundColor(Theme.CARD)
          .borderRadius(Theme.RADIUS)
          .alignItems(HorizontalAlign.Start)
        }

        // 今日建议
        Text('今日建议')
          .fontSize(15)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
          .width('100%')
          .margin({ top: 4 })

        Column({ space: 10 }) {
          this.suggestion('🎥', '自习后看一条 3 分钟视频', '把今天卡住的点交给下一位同学')
          this.suggestion('⏱️', '50 分钟专注 + 10 分钟休息', '保持节奏，比一次坐 3 小时更有效')
          this.suggestion('🪑', '优先选靠窗安静位', '在「空间」里按 靠窗 / 安静 / 电源 筛选')
        }
        .width('100%')

        // 最近接棒
        if (this.pushes.length > 0) {
          Text('最近的学习接力')
            .fontSize(15)
            .fontWeight(FontWeight.Medium)
            .fontColor(Theme.TEXT)
            .width('100%')
            .margin({ top: 4 })
          this.relayCard(this.pushes[0])
        }

        Blank().height(20)
      }
      .width('100%')
      .padding(14)
    }
    .scrollBar(BarState.Off)
    .width('100%')
    .height('100%')
    .backgroundColor(Theme.BG)
  }

  @Builder
  relayCard(p: RelayPush) {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        Text('🔁')
          .fontSize(18)
        Text(p.title ? p.title : '学习接力')
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
          .layoutWeight(1)
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
        Text(p.feedback === 'helpful' ? '有帮助' : (p.feedback === 'unhelpful' ? '没帮助' : '待反馈'))
          .fontSize(11)
          .fontColor(p.feedback === 'helpful' ? Theme.SUCCESS : Theme.TEXT_FAINT)
      }
      .width('100%')

      Text(p.reason ? p.reason : '为你匹配到一条已过审学习视频')
        .fontSize(12)
        .fontColor(Theme.TEXT_SUB)
        .maxLines(2)
        .textOverflow({ overflow: TextOverflow.Ellipsis })

      Row() {
        Text((p.subject ? p.subject : '') + ' · ' + Fmt.durationText(p.duration_sec))
          .fontSize(11)
          .fontColor(Theme.TEXT_FAINT)
        Blank()
        Text('去反馈')
          .fontSize(12)
          .fontColor(Theme.ACCENT)
          .onClick(() => {
            AppStorage.setOrCreate('tab', 2);
          })
      }
      .width('100%')
    }
    .width('100%')
    .padding(14)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(HorizontalAlign.Start)
  }
}