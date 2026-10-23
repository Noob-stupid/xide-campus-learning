import { Api } from '../net/Api';
import { Theme } from '../common/Theme';
import { Fmt } from '../common/Format';
import { StudySession, RelayPush, ReservationInfo } from '../model/Types';

/** 学习页：计时、签到、卡住了辅导、结束、接棒反馈 */
@Component
export struct LearnView {
  @State session: StudySession | null = null;
  @State pending: ReservationInfo | null = null;
  @State pushes: RelayPush[] = [];
  @State tick: number = 0;
  @State msg: string = '';
  @State loading: boolean = true;
  // 辅导
  @State tutorActive: boolean = false;
  @State tutorId: string = '';
  @State tutorQ: string = '';
  @State tutorOptions: string[] = [];
  @State tutorDone: boolean = false;
  @State tutorExp: string = '';
  @State tutorResource: string = '';
  private timer: number = -1;

  aboutToAppear(): void {
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
    try {
      const cs = await Api.currentSession();
      this.session = cs.session ?? null;
      const rs = await Api.myReservations();
      let p: ReservationInfo | null = null;
      if (rs.ok && rs.reservations) {
        for (let i = 0; i < rs.reservations.length; i++) {
          if (rs.reservations[i].status === 'booked') {
            p = rs.reservations[i];
            break;
          }
        }
      }
      this.pending = p;
      const pu = await Api.relayPending();
      this.pushes = pu.ok && pu.pushes ? pu.pushes : [];
    } catch (e) {
      this.msg = '加载失败，请重试';
    } finally {
      this.loading = false;
    }
  }

  async doCheckin(): Promise<void> {
    if (!this.pending) {
      return;
    }
    try {
      const r = await Api.checkin((this.pending as ReservationInfo).id);
      if (r.ok) {
        this.msg = '签到成功，开始计时';
        await this.load();
      } else {
        this.msg = r.error ? r.error : '签到失败';
      }
    } catch (e) {
      this.msg = '签到失败，请重试';
    }
  }

  async endStudy(): Promise<void> {
    if (!this.session) {
      return;
    }
    try {
      const r = await Api.endBooking((this.session as StudySession).reservation_id);
      if (r.ok) {
        this.msg = '已结束，正在为你匹配学习视频';
        await this.load();
      }
    } catch (e) {
      this.msg = '结束失败，请重试';
    }
  }

  async startTutor(): Promise<void> {
    this.tutorActive = true;
    this.tutorDone = false;
    this.tutorResource = '';
    this.msg = '';
    try {
      const r = await Api.tutorStart('高数极限');
      this.tutorId = r.tutor_id ? r.tutor_id : 'local';
      this.tutorQ = r.question ? r.question : '';
      this.tutorOptions = r.options ? r.options : [];
    } catch (e) {
      this.msg = '辅导启动失败';
    }
  }

  async answerTutor(text: string): Promise<void> {
    try {
      const r = await Api.tutorAnswer(this.tutorId, text);
      if (r.done) {
        this.tutorDone = true;
        this.tutorExp = r.explanation ? r.explanation : '';
        this.tutorQ = r.check_question ? r.check_question : '';
        this.tutorOptions = [];
        if (r.resource) {
          this.tutorResource = r.resource.title ? r.resource.title : '';
        }
      } else {
        this.tutorQ = r.question ? r.question : '';
        this.tutorOptions = r.options ? r.options : [];
      }
    } catch (e) {
      this.msg = '回答失败，请重试';
    }
  }

  async feedback(pid: number, value: string): Promise<void> {
    try {
      const r = await Api.relayFeedback(pid, value);
      if (r.ok) {
        this.msg = '感谢你的反馈';
        await this.load();
      }
    } catch (e) {
      this.msg = '反馈失败';
    }
  }

  seatCodeText(): string {
    return this.session && this.session.seat_code ? this.session.seat_code : '';
  }

  sessionSubject(): string {
    return this.session && this.session.subject ? this.session.subject : '自主学习';
  }

  sessionStartedAt(): string {
    return this.session ? this.session.started_at : '';
  }

  pendingSeatText(): string {
    if (!this.pending) {
      return '';
    }
    const s = this.pending as ReservationInfo;
    return '座位 ' + (s.seat_code ? s.seat_code : '') + ' · ' + (s.subject ? s.subject : '');
  }

  pendingTimeText(): string {
    if (!this.pending) {
      return '';
    }
    const s = this.pending as ReservationInfo;
    return '预约时段 ' + Fmt.hhmm(s.start_at) + ' - ' + Fmt.hhmm(s.end_at);
  }

  build() {
    Scroll() {
      Column({ space: 12 }) {
        Text('学习')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.TEXT)
          .width('100%')

        if (this.msg.length > 0) {
          Text(this.msg)
            .fontSize(13)
            .fontColor(Theme.ACCENT)
            .width('100%')
            .padding(10)
            .backgroundColor(Theme.ACCENT_SOFT)
            .borderRadius(Theme.RADIUS_SM)
        }

        // 计时卡
        if (this.session) {
          Column({ space: 10 }) {
            Row() {
              Text('专注计时')
                .fontSize(13)
                .fontColor(Theme.TEXT_SUB)
              Blank()
              Text(this.seatCodeText())
                .fontSize(13)
                .fontColor(Theme.ACCENT)
            }
            .width('100%')
            Text(Fmt.clock(Fmt.elapsedSec(this.sessionStartedAt())))
              .fontSize(40)
              .fontWeight(FontWeight.Bold)
              .fontColor(Theme.PRIMARY)
            Text('50 分钟专注 + 10 分钟休息 · ' + this.sessionSubject())
              .fontSize(12)
              .fontColor(Theme.TEXT_SUB)

            Row({ space: 10 }) {
              Button('卡住了，帮帮我')
                .layoutWeight(1)
                .height(42)
                .backgroundColor(Theme.ACCENT)
                .fontColor(Theme.WHITE)
                .onClick(() => {
                  this.startTutor();
                })
              Button('结束学习')
                .width(110)
                .height(42)
                .backgroundColor('#FBE9EA')
                .fontColor(Theme.DANGER)
                .onClick(() => {
                  this.endStudy();
                })
            }
            .width('100%')
          }
          .width('100%')
          .padding(16)
          .backgroundColor(Theme.CARD)
          .borderRadius(Theme.RADIUS)
          .alignItems(HorizontalAlign.Start)
        } else if (this.pending) {
          Column({ space: 10 }) {
            Text('待签到')
              .fontSize(13)
              .fontColor(Theme.TEXT_SUB)
            Text(this.pendingSeatText())
              .fontSize(16)
              .fontWeight(FontWeight.Medium)
              .fontColor(Theme.TEXT)
            Text(this.pendingTimeText())
              .fontSize(12)
              .fontColor(Theme.TEXT_SUB)
            Button('到场签到，开始学习')
              .width('100%')
              .height(44)
              .backgroundColor(Theme.PRIMARY)
              .fontColor(Theme.WHITE)
              .onClick(() => {
                this.doCheckin();
              })
          }
          .width('100%')
          .padding(16)
          .backgroundColor(Theme.CARD)
          .borderRadius(Theme.RADIUS)
          .alignItems(HorizontalAlign.Start)
        } else {
          Column({ space: 10 }) {
            Text('还没有进行中的学习')
              .fontSize(14)
              .fontColor(Theme.TEXT_SUB)
            Button('先去空间找个座位')
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

        // 辅导面板
        if (this.tutorActive) {
          this.tutorBox()
        }

        // 接棒卡
        if (this.pushes.length > 0) {
          Text('学习接力')
            .fontSize(15)
            .fontWeight(FontWeight.Medium)
            .fontColor(Theme.TEXT)
            .width('100%')
            .margin({ top: 4 })
          ForEach(this.pushes, (p: RelayPush) => {
            this.relayItem(p)
          }, (p: RelayPush) => p.id.toString())
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
  tutorBox() {
    Column({ space: 10 }) {
      Row() {
        Text('🤔 卡住了辅导')
          .fontSize(15)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
        Blank()
        Text('关闭')
          .fontSize(12)
          .fontColor(Theme.TEXT_FAINT)
          .onClick(() => {
            this.tutorActive = false;
          })
      }
      .width('100%')

      Text(this.tutorQ)
        .fontSize(14)
        .fontColor(Theme.TEXT)
        .width('100%')

      if (this.tutorDone) {
        if (this.tutorExp.length > 0) {
          Text(this.tutorExp)
            .fontSize(13)
            .fontColor(Theme.TEXT_SUB)
            .width('100%')
            .padding(10)
            .backgroundColor('#F5F7FA')
            .borderRadius(Theme.RADIUS_SM)
        }
        if (this.tutorResource.length > 0) {
          Text('配套视频：' + this.tutorResource)
            .fontSize(13)
            .fontColor(Theme.ACCENT)
            .width('100%')
        }
        if (this.tutorQ.length > 0) {
          Text('再想一想：' + this.tutorQ)
            .fontSize(13)
            .fontColor(Theme.TEXT)
            .width('100%')
        }
      } else {
        ForEach(this.tutorOptions, (opt: string) => {
          Button(opt)
            .width('100%')
            .height(42)
            .backgroundColor('#EDF1F7')
            .fontColor(Theme.PRIMARY)
            .onClick(() => {
              this.answerTutor(opt);
            })
        }, (opt: string) => opt)
      }
    }
    .width('100%')
    .padding(14)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  relayItem(p: RelayPush) {
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
      }
      .width('100%')

      Text(p.reason ? p.reason : '为你匹配到一条已过审学习视频')
        .fontSize(12)
        .fontColor(Theme.TEXT_SUB)
        .maxLines(2)
        .textOverflow({ overflow: TextOverflow.Ellipsis })

      Text((p.subject ? p.subject : '') + ' · ' + Fmt.durationText(p.duration_sec) +
        (p.owner_name ? ' · 来自 ' + p.owner_name : ''))
        .fontSize(11)
        .fontColor(Theme.TEXT_FAINT)

      if (p.feedback === 'helpful' || p.feedback === 'unhelpful') {
        Text(p.feedback === 'helpful' ? '已反馈：有帮助' : '已反馈：没帮助')
          .fontSize(12)
          .fontColor(p.feedback === 'helpful' ? Theme.SUCCESS : Theme.TEXT_FAINT)
      } else {
        Row({ space: 10 }) {
          Button('有帮助')
            .layoutWeight(1)
            .height(38)
            .backgroundColor(Theme.SUCCESS)
            .fontColor(Theme.WHITE)
            .onClick(() => {
              this.feedback(p.id, 'helpful');
            })
          Button('没帮助')
            .layoutWeight(1)
            .height(38)
            .backgroundColor('#EDF1F7')
            .fontColor(Theme.TEXT_SUB)
            .onClick(() => {
              this.feedback(p.id, 'unhelpful');
            })
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding(14)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(HorizontalAlign.Start)
  }
}