import { Api } from '../net/Api';
import { Theme } from '../common/Theme';
import { NavPathNode } from '../model/Types';
import { router } from '@kit.ArkUI';

interface NavParams {
  seatId?: number;
  seatCode?: string;
}

/** 导航页：A* 室内路径（Canvas 绘制）+ 分步指引 */
@Entry
@Component
struct NavPage {
  @State seatId: number = 0;
  @State seatCode: string = '';
  @State path: NavPathNode[] = [];
  @State steps: string[] = [];
  @State distance: number = 0;
  @State minutes: number = 0;
  @State loading: boolean = true;
  @State err: string = '';
  @State planW: number = 960;
  @State planH: number = 620;
  @State ready: boolean = false;
  private settings: RenderingContextSettings = new RenderingContextSettings(true);
  private ctx: CanvasRenderingContext2D = new CanvasRenderingContext2D(this.settings);

  aboutToAppear(): void {
    const p = router.getParams() as NavParams;
    if (p) {
      if (p.seatId) {
        this.seatId = p.seatId;
      }
      if (p.seatCode) {
        this.seatCode = p.seatCode;
      }
    }
    this.load();
  }

  async load(): Promise<void> {
    this.loading = true;
    this.err = '';
    try {
      const r = await Api.nav(this.seatId, 'entry');
      if (r.ok) {
        this.path = r.path ? r.path : [];
        this.steps = r.steps ? r.steps : [];
        this.distance = r.distance ? r.distance : 0;
        this.minutes = r.minutes ? r.minutes : 0;
        if (r.seat) {
          this.seatCode = r.seat.code;
        }
        if (r.floor) {
          this.planW = r.floor.plan_w;
          this.planH = r.floor.plan_h;
        }
        if (this.ready) {
          this.draw();
        }
      } else {
        this.err = r.error ? r.error : '导航生成失败';
      }
    } catch (e) {
      this.err = '网络错误，请检查 BASE_URL';
    } finally {
      this.loading = false;
    }
  }

  draw(): void {
    const ctx = this.ctx;
    const w: number = ctx.width;
    const h: number = ctx.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#EAF0F7';
    ctx.fillRect(0, 0, w, h);

    const pts: NavPathNode[] = this.path;
    if (pts.length === 0) {
      return;
    }
    const scale: number = w / this.planW;

    // 连线
    ctx.strokeStyle = '#2F80ED';
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (let i = 0; i < pts.length; i++) {
      const x: number = pts[i].x * scale;
      const y: number = pts[i].y * scale;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    // 节点
    for (let i = 0; i < pts.length; i++) {
      const x: number = pts[i].x * scale;
      const y: number = pts[i].y * scale;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      if (i === 0) {
        ctx.fillStyle = '#3FAE6B';
      } else if (i === pts.length - 1) {
        ctx.fillStyle = '#D9534F';
      } else {
        ctx.fillStyle = '#2F80ED';
      }
      ctx.fill();
    }
  }

  build() {
    Column({ space: 12 }) {
      Row() {
        Text('←')
          .fontSize(22)
          .fontColor(Theme.TEXT)
          .onClick(() => {
            router.back();
          })
        Text('导航到 ' + (this.seatCode.length > 0 ? this.seatCode : '座位'))
          .fontSize(17)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.TEXT)
          .margin({ left: 10 })
        Text('室外导航')
          .fontSize(12)
          .fontColor(Theme.PRIMARY)
          .margin({ right: 10 })
          .onClick(() => {
            router.pushUrl({ url: 'pages/OutdoorPage' });
          })
        Blank()
      }
      .width('100%')

      if (this.err.length > 0) {
        Text(this.err)
          .fontSize(13)
          .fontColor(Theme.DANGER)
          .width('100%')
      }

      Canvas(this.ctx)
        .width('100%')
        .aspectRatio(this.planW / this.planH)
        .backgroundColor('#EAF0F7')
        .borderRadius(Theme.RADIUS)
        .onReady(() => {
          this.ready = true;
          this.draw();
        })

      Row({ space: 12 }) {
        Column({ space: 2 }) {
          Text(this.distance.toString() + ' 米')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Theme.PRIMARY)
          Text('步行距离')
            .fontSize(11)
            .fontColor(Theme.TEXT_SUB)
        }
        .layoutWeight(1)
        .alignItems(HorizontalAlign.Start)

        Column({ space: 2 }) {
          Text(this.minutes.toString() + ' 分钟')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Theme.PRIMARY)
          Text('预计时间')
            .fontSize(11)
            .fontColor(Theme.TEXT_SUB)
        }
        .layoutWeight(1)
        .alignItems(HorizontalAlign.Start)
      }
      .width('100%')
      .padding(14)
      .backgroundColor(Theme.CARD)
      .borderRadius(Theme.RADIUS)

      Text('行走指引')
        .fontSize(15)
        .fontWeight(FontWeight.Medium)
        .fontColor(Theme.TEXT)
        .width('100%')

      List({ space: 8 }) {
        ForEach(this.steps, (s: string, idx: number) => {
          ListItem() {
            Row({ space: 10 }) {
              Text((idx + 1).toString())
                .fontSize(12)
                .fontColor(Theme.WHITE)
                .width(22)
                .height(22)
                .textAlign(TextAlign.Center)
                .backgroundColor(Theme.ACCENT)
                .borderRadius(11)
              Text(s)
                .fontSize(13)
                .fontColor(Theme.TEXT)
              Blank()
            }
            .width('100%')
            .padding(12)
            .backgroundColor(Theme.CARD)
            .borderRadius(Theme.RADIUS_SM)
          }
        }, (s: string, idx: number) => idx.toString() + s)
      }
      .layoutWeight(1)
      .width('100%')
      .scrollBar(BarState.Off)
    }
    .width('100%')
    .height('100%')
    .padding(14)
    .backgroundColor(Theme.BG)
  }
}