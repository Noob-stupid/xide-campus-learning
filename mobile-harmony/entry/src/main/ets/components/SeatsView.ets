import { Api } from '../net/Api';
import { Theme } from '../common/Theme';
import { Fmt } from '../common/Format';
import { FloorInfo, SeatInfo } from '../model/Types';
import { router } from '@kit.ArkUI';

interface NavParams {
  seatId: number;
  seatCode: string;
}

/** 空间页：先选建筑/楼层，再看座位图、筛选、点选、预约 */
@Component
export struct SeatsView {
  @State floors: FloorInfo[] = [];
  @State buildings: string[] = [];
  @State activeBuilding: string = '';
  @State activeFloorId: number = 0;
  @State seats: SeatInfo[] = [];
  @State filter: string = 'all';
  @State selected: SeatInfo | null = null;
  @State loading: boolean = true;
  @State err: string = '';
  @State planW: number = 960;
  @State planH: number = 620;
  @State seatScale: number = 0.42;

  // 预约表单
  @State subject: string = '高等数学';
  @State goal: string = '';
  @State startAt: string = '';
  @State endAt: string = '';
  @State booking: boolean = false;
  @State bookingMsg: string = '';

  aboutToAppear(): void {
    this.loadFloors();
  }

  async loadFloors(): Promise<void> {
    this.loading = true;
    this.err = '';
    try {
      const r = await Api.floors();
      if (r.ok && r.floors) {
        this.floors = r.floors;
        const bs: string[] = [];
        for (let i = 0; i < r.floors.length; i++) {
          const b = r.floors[i].building;
          if (bs.indexOf(b) < 0) {
            bs.push(b);
          }
        }
        this.buildings = bs;
        if (bs.length > 0) {
          this.activeBuilding = bs[0];
          const aid = this.firstFloorOf(bs[0]);
          this.activeFloorId = aid;
          await this.loadSeats();
        }
      } else {
        this.err = r.error ? r.error : '楼层加载失败';
      }
    } catch (e) {
      this.err = '网络错误，请检查 BASE_URL';
    } finally {
      this.loading = false;
    }
  }

  firstFloorOf(building: string): number {
    for (let i = 0; i < this.floors.length; i++) {
      if (this.floors[i].building === building) {
        return this.floors[i].id;
      }
    }
    return 0;
  }

  buildingFloors(): FloorInfo[] {
    const out: FloorInfo[] = [];
    for (let i = 0; i < this.floors.length; i++) {
      if (this.floors[i].building === this.activeBuilding) {
        out.push(this.floors[i]);
      }
    }
    return out;
  }

  curFloor(): FloorInfo | null {
    for (let i = 0; i < this.floors.length; i++) {
      if (this.floors[i].id === this.activeFloorId) {
        return this.floors[i];
      }
    }
    return null;
  }

  async loadSeats(): Promise<void> {
    const f = this.curFloor();
    if (f) {
      this.planW = f.plan_w;
      this.planH = f.plan_h;
    }
    try {
      const r = await Api.seats(this.activeFloorId);
      if (r.ok && r.seats) {
        this.seats = r.seats;
      } else {
        this.err = r.error ? r.error : '座位加载失败';
      }
    } catch (e) {
      this.err = '座位加载失败，请重试';
    }
  }

  visibleSeats(): SeatInfo[] {
    if (this.filter === 'all') {
      return this.seats;
    }
    const out: SeatInfo[] = [];
    for (let i = 0; i < this.seats.length; i++) {
      const s = this.seats[i];
      if (s.features && s.features.indexOf(this.filter) >= 0) {
        out.push(s);
      }
    }
    return out;
  }

  recommendText(): string {
    for (let i = 0; i < this.seats.length; i++) {
      const s = this.seats[i];
      if (s.live_status === 'free' && s.features && s.features.indexOf('window') >= 0) {
        return '推荐 ' + s.code + '：靠窗、安静，当前空闲';
      }
    }
    return '';
  }

  seatColor(s: string): string {
    if (s === 'free') {
      return Theme.FREE;
    }
    if (s === 'booked') {
      return Theme.BOOKED;
    }
    if (s === 'using') {
      return Theme.USING;
    }
    return Theme.MAINT;
  }

  stamp(d: Date): string {
    return d.getFullYear() + '-' + Fmt.pad2(d.getMonth() + 1) + '-' + Fmt.pad2(d.getDate()) + ' ' +
      Fmt.pad2(d.getHours()) + ':' + Fmt.pad2(d.getMinutes()) + ':' + Fmt.pad2(d.getSeconds());
  }

  nowPlus(min: number): string {
    return this.stamp(new Date(Date.now() + min * 60000));
  }

  pick(s: SeatInfo): void {
    this.bookingMsg = '';
    if (s.live_status === 'maintenance') {
      this.selected = null;
      this.bookingMsg = '该座位维护中，请换一个';
      return;
    }
    if (s.live_status !== 'free' && !s.mine) {
      this.selected = null;
      this.bookingMsg = '该座位已被占用';
      return;
    }
    this.selected = s;
    this.startAt = this.nowPlus(0);
    this.endAt = this.nowPlus(60);
  }

  async confirmBook(): Promise<void> {
    if (!this.selected || this.booking) {
      return;
    }
    this.booking = true;
    this.bookingMsg = '';
    try {
      const s = this.selected as SeatInfo;
      const r = await Api.book(s.id, this.subject, this.goal, this.startAt, this.endAt);
      if (r.ok) {
        this.bookingMsg = '预约成功！到场后可签到';
        this.selected = null;
        await this.loadSeats();
      } else {
        this.bookingMsg = r.error ? r.error : '预约失败';
      }
    } catch (e) {
      this.bookingMsg = '预约失败，请重试';
    } finally {
      this.booking = false;
    }
  }

  @Builder
  chip(text: string, key: string) {
    Text(text)
      .fontSize(12)
      .fontColor(this.filter === key ? Theme.WHITE : Theme.TEXT_SUB)
      .padding({ left: 12, right: 12, top: 6, bottom: 6 })
      .backgroundColor(this.filter === key ? Theme.PRIMARY : Theme.CARD)
      .borderRadius(20)
      .onClick(() => {
        this.filter = key;
      })
  }

  @Builder
  buildingTab(b: string) {
    Column({ space: 4 }) {
      Text(b)
        .fontSize(13)
        .fontWeight(this.activeBuilding === b ? FontWeight.Medium : FontWeight.Normal)
        .fontColor(this.activeBuilding === b ? Theme.PRIMARY : Theme.TEXT_SUB)
      Row()
        .width(18)
        .height(3)
        .borderRadius(2)
        .backgroundColor(this.activeBuilding === b ? Theme.PRIMARY : Color.Transparent)
    }
    .margin({ right: 18 })
    .padding({ top: 8, bottom: 4 })
    .onClick(() => {
      this.activeBuilding = b;
      const fid = this.firstFloorOf(b);
      this.activeFloorId = fid;
      this.selected = null;
      this.loadSeats();
    })
  }

  @Builder
  floorTab(f: FloorInfo) {
    Text(f.floor_no.toString() + 'F')
      .fontSize(12)
      .fontColor(this.activeFloorId === f.id ? Theme.WHITE : Theme.PRIMARY)
      .backgroundColor(this.activeFloorId === f.id ? Theme.PRIMARY : '#E8EEF6')
      .padding({ left: 12, right: 12, top: 6, bottom: 6 })
      .borderRadius(16)
      .margin({ right: 8 })
      .onClick(() => {
        this.activeFloorId = f.id;
        this.selected = null;
        this.loadSeats();
      })
  }

  private shortCode(code: string): string {
    const c: string = code.replace('-', '');
    if (c.length === 3 && c.charAt(1) === '0') {
      return c.charAt(0) + c.charAt(2);
    }
    return c;
  }

  @Builder
  seatCell(s: SeatInfo) {
    Text(s.code.replace('-', '').substring(1))
      .fontSize(7)
      .fontColor(Theme.WHITE)
      .textAlign(TextAlign.Center)
      .maxLines(1)
      .textOverflow({ overflow: TextOverflow.Clip })
      .width(s.w * this.seatScale)
      .height(s.h * this.seatScale)
      .backgroundColor(this.seatColor(s.live_status))
      .borderRadius(2)
      .border(this.selected && this.selected.id === s.id
        ? { width: 2, color: Theme.ACCENT }
        : { width: 0, color: Color.Transparent })
      .position({ x: s.x * this.seatScale, y: s.y * this.seatScale })
      .onClick(() => {
        this.pick(s);
      })
  }

  build() {
    Column({ space: 10 }) {
      Text('空间找座')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(Theme.TEXT)
        .width('100%')

      // 建筑
      Row() {
        ForEach(this.buildings, (b: string) => {
          this.buildingTab(b)
        }, (b: string) => b)
      }
      .width('100%')

      // 楼层
      Row() {
        ForEach(this.buildingFloors(), (f: FloorInfo) => {
          this.floorTab(f)
        }, (f: FloorInfo) => f.id.toString())
      }
      .width('100%')

      // 筛选
      Row({ space: 8 }) {
        this.chip('全部', 'all')
        this.chip('靠窗', 'window')
        this.chip('安静', 'quiet')
        this.chip('电源', 'power')
      }
      .width('100%')

      if (this.recommendText().length > 0) {
        Text(this.recommendText())
          .fontSize(12)
          .fontColor(Theme.ACCENT)
          .width('100%')
          .padding({ left: 10, right: 10, top: 8, bottom: 8 })
          .backgroundColor(Theme.ACCENT_SOFT)
          .borderRadius(Theme.RADIUS_SM)
      }

      // 图例
      Row({ space: 12 }) {
        this.legend('空闲', Theme.FREE)
        this.legend('已预约', Theme.BOOKED)
        this.legend('使用中', Theme.USING)
        this.legend('维护', Theme.MAINT)
      }
      .width('100%')

      // 座位图
      Scroll() {
        Scroll() {
          Stack() {
            ForEach(this.visibleSeats(), (s: SeatInfo) => {
              this.seatCell(s)
            }, (s: SeatInfo) => s.id.toString())
          }
          .width(this.planW * this.seatScale)
          .height(this.planH * this.seatScale)
        }
        .scrollable(ScrollDirection.Horizontal)
        .width('100%')
      }
      .scrollable(ScrollDirection.Vertical)
      .layoutWeight(1)
      .width('100%')
      .backgroundColor('#EAF0F7')
      .borderRadius(Theme.RADIUS)

      if (this.bookingMsg.length > 0) {
        Text(this.bookingMsg)
          .fontSize(13)
          .fontColor(this.bookingMsg.indexOf('成功') >= 0 ? Theme.SUCCESS : Theme.DANGER)
          .width('100%')
      }

      // 预约表单
      if (this.selected) {
        this.bookSheet(this.selected as SeatInfo)
      }

      Blank().height(8)
    }
    .width('100%')
    .height('100%')
    .padding(14)
    .backgroundColor(Theme.BG)
  }

  @Builder
  legend(text: string, color: string) {
    Row({ space: 4 }) {
      Row()
        .width(10)
        .height(10)
        .backgroundColor(color)
        .borderRadius(2)
      Text(text)
        .fontSize(11)
        .fontColor(Theme.TEXT_SUB)
    }
  }

  @Builder
  bookSheet(s: SeatInfo) {
    Column({ space: 10 }) {
      Row() {
        Text(s.code + ' · ' + s.zone)
          .fontSize(15)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
        Blank()
        Text(Fmt.seatStatusText(s.live_status))
          .fontSize(12)
          .fontColor(this.seatColor(s.live_status))
      }
      .width('100%')

      if (s.features && s.features.length > 0) {
        Row({ space: 8 }) {
          ForEach(s.features, (f: string) => {
            Text(Fmt.featureText(f))
              .fontSize(11)
              .fontColor(Theme.PRIMARY)
              .padding({ left: 8, right: 8, top: 3, bottom: 3 })
              .backgroundColor('#E8EEF6')
              .borderRadius(10)
          }, (f: string) => f)
        }
        .width('100%')
      }

      if (s.mine) {
        Button('查看导航')
          .width('100%')
          .height(42)
          .backgroundColor(Theme.PRIMARY)
          .fontColor(Theme.WHITE)
          .onClick(() => {
            const np: NavParams = { seatId: s.id, seatCode: s.code };
            router.pushUrl({ url: 'pages/NavPage', params: np });
          })
      } else {
        TextInput({ placeholder: '学科学什么（如：高等数学）', text: this.subject })
          .height(44)
          .backgroundColor('#F5F7FA')
          .borderRadius(Theme.RADIUS_SM)
          .onChange((v: string) => {
            this.subject = v;
          })
        TextInput({ placeholder: '这次想解决什么（可选）', text: this.goal })
          .height(44)
          .backgroundColor('#F5F7FA')
          .borderRadius(Theme.RADIUS_SM)
          .onChange((v: string) => {
            this.goal = v;
          })

        Row({ space: 8 }) {
          this.quick(60)
          this.quick(90)
          this.quick(120)
        }
        .width('100%')

        Text('开始 ' + Fmt.hhmm(this.startAt) + ' → 结束 ' + Fmt.hhmm(this.endAt))
          .fontSize(12)
          .fontColor(Theme.TEXT_SUB)
          .width('100%')

        Row({ space: 10 }) {
          Button('确认预约')
            .layoutWeight(1)
            .height(44)
            .backgroundColor(Theme.PRIMARY)
            .fontColor(Theme.WHITE)
            .enabled(!this.booking)
            .onClick(() => {
              this.confirmBook();
            })
          Button('取消')
            .width(80)
            .height(44)
            .backgroundColor('#EDF1F7')
            .fontColor(Theme.TEXT_SUB)
            .onClick(() => {
              this.selected = null;
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

  @Builder
  quick(min: number) {
    Text(min.toString() + ' 分钟')
      .fontSize(12)
      .fontColor(Theme.PRIMARY)
      .padding({ left: 10, right: 10, top: 5, bottom: 5 })
      .backgroundColor('#E8EEF6')
      .borderRadius(14)
      .onClick(() => {
        this.endAt = this.nowPlus(min);
      })
  }
}