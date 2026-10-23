import { Api } from '../net/Api';
import { Theme } from '../common/Theme';
import { BuildingInfo, OutdoorResp } from '../model/Types';
import { router } from '@kit.ArkUI';
import { common, Want } from '@kit.AbilityKit';

/** 室外导航：校门/当前位置 → 图书馆/教学楼，显示距离、方向、步行时间和步骤。 */
@Entry
@Component
struct OutdoorPage {
  @State buildings: BuildingInfo[] = [];
  @State active: string = '';
  @State data: OutdoorResp | null = null;
  @State loading: boolean = true;
  @State err: string = '';

  aboutToAppear(): void {
    this.load();
  }

  async load(): Promise<void> {
    this.loading = true;
    this.err = '';
    try {
      const r = await Api.outdoor(this.active);
      if (r.ok) {
        this.data = r;
        if (r.buildings && r.buildings.length > 0) {
          this.buildings = r.buildings;
          if (this.active.length === 0) {
            this.active = r.buildings[0].name;
          }
        }
      } else {
        this.err = r.error ? r.error : '路线加载失败';
      }
    } catch (e) {
      this.err = '网络错误，请检查 BASE_URL 与 HTTPS';
    } finally {
      this.loading = false;
    }
  }

  pick(name: string): void {
    this.active = name;
    this.load();
  }

  distText(): string {
    return this.data && this.data.distance_m !== undefined ? this.data.distance_m.toString() : '—';
  }

  minutesText(): string {
    return this.data && this.data.minutes !== undefined ? this.data.minutes.toString() : '—';
  }

  directionText(): string {
    return this.data && this.data.direction ? this.data.direction : '—';
  }

  steps(): string[] {
    return this.data && this.data.steps ? this.data.steps : [];
  }

  openAmap(): void {
    const uri: string = this.data && this.data.amap_uri ? this.data.amap_uri : '';
    if (uri.length === 0) {
      return;
    }
    const ctx = getContext(this) as common.UIAbilityContext;
    const want: Want = { action: 'ohos.want.action.viewData', uri: uri };
    ctx.startAbility(want).catch(() => {
      this.err = '没有找到可打开地图的应用';
    });
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
        Text('室外导航')
          .fontSize(17)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.TEXT)
          .margin({ left: 10 })
        Blank()
        Text('室内导航')
          .fontSize(12)
          .fontColor(Theme.PRIMARY)
          .onClick(() => {
            router.back();
          })
      }
      .width('100%')

      if (this.err.length > 0) {
        Text(this.err)
          .fontSize(13)
          .fontColor(Theme.DANGER)
          .width('100%')
      }

      Scroll() {
        Row() {
          ForEach(this.buildings, (b: BuildingInfo) => {
            Text(b.name)
              .fontSize(12)
              .fontColor(this.active === b.name ? Theme.WHITE : Theme.TEXT_SUB)
              .padding({ left: 12, right: 12, top: 7, bottom: 7 })
              .backgroundColor(this.active === b.name ? Theme.PRIMARY : Theme.CARD)
              .borderRadius(18)
              .margin({ right: 8 })
              .onClick(() => {
                this.pick(b.name);
              })
          }, (b: BuildingInfo) => b.id.toString())
        }
      }
      .scrollable(ScrollDirection.Horizontal)
      .scrollBar(BarState.Off)
      .width('100%')

      Column({ space: 6 }) {
        Text(this.active.length > 0 ? this.active : '选择目的地')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.WHITE)
        Text('从校门演示坐标出发；接原生定位后可换成当前位置')
          .fontSize(11)
          .fontColor('#B9C7DB')
      }
      .width('100%')
      .padding(16)
      .backgroundColor(Theme.PRIMARY)
      .borderRadius(Theme.RADIUS)
      .alignItems(HorizontalAlign.Start)

      Row({ space: 10 }) {
        Column({ space: 2 }) {
          Text(this.distText() + ' 米')
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
          Text(this.minutesText() + ' 分钟')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Theme.PRIMARY)
          Text('预计时间')
            .fontSize(11)
            .fontColor(Theme.TEXT_SUB)
        }
        .layoutWeight(1)
        .alignItems(HorizontalAlign.Start)

        Column({ space: 2 }) {
          Text(this.directionText())
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Theme.PRIMARY)
          Text('方向')
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

      Text('步行指引')
        .fontSize(15)
        .fontWeight(FontWeight.Medium)
        .fontColor(Theme.TEXT)
        .width('100%')

      List({ space: 8 }) {
        ForEach(this.steps(), (s: string, idx: number) => {
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

      Button('在高德地图中打开')
        .width('100%')
        .height(44)
        .backgroundColor(Theme.PRIMARY)
        .fontColor(Theme.WHITE)
        .onClick(() => {
          this.openAmap();
        })
    }
    .width('100%')
    .height('100%')
    .padding(14)
    .backgroundColor(Theme.BG)
  }
}
