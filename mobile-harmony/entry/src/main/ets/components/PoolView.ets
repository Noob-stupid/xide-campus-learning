import { Api, BASE_URL } from '../net/Api';
import { Theme } from '../common/Theme';
import { Fmt } from '../common/Format';
import { ContentInfo } from '../model/Types';
import { router } from '@kit.ArkUI';

/** 接力池：只看已过审内容，按学科筛选 */
@Component
export struct PoolView {
  @State items: ContentInfo[] = [];
  @State subject: string = '';
  @State loading: boolean = true;
  @State msg: string = '';
  private subjects: string[] = ['全部', '高等数学', '英语', '编程', '学习方法'];

  aboutToAppear(): void {
    this.load();
  }

  async load(): Promise<void> {
    this.loading = true;
    this.msg = '';
    try {
      const r = await Api.contents('approved', this.subject);
      if (r.ok && r.contents) {
        this.items = r.contents;
      } else {
        this.items = [];
        if (r.error) {
          this.msg = r.error;
        }
      }
    } catch (e) {
      this.msg = '加载失败，请检查网络';
    } finally {
      this.loading = false;
    }
  }

  pick(s: string): void {
    this.subject = s === '全部' ? '' : s;
    this.load();
  }

  coverUrl(c: ContentInfo): string {
    if (c.cover_url && c.cover_url.length > 0) {
      return BASE_URL + c.cover_url;
    }
    return '';
  }

  @Builder
  chip(text: string) {
    Text(text)
      .fontSize(12)
      .fontColor((text === '全部' && this.subject.length === 0) || this.subject === text ? Theme.WHITE : Theme.TEXT_SUB)
      .padding({ left: 12, right: 12, top: 6, bottom: 6 })
      .backgroundColor((text === '全部' && this.subject.length === 0) || this.subject === text ? Theme.PRIMARY : Theme.CARD)
      .borderRadius(20)
      .margin({ right: 8 })
      .onClick(() => {
        this.pick(text);
      })
  }

  build() {
    Column({ space: 12 }) {
      Row() {
        Text('接力池')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.TEXT)
        Blank()
        Button('交棒')
          .fontSize(12)
          .height(30)
          .backgroundColor(Theme.PRIMARY)
          .fontColor(Theme.WHITE)
          .onClick(() => {
            router.pushUrl({ url: 'pages/WebShell', params: { path: '/upload' } });
          })
      }
      .width('100%')

      Scroll() {
        Row() {
          ForEach(this.subjects, (s: string) => {
            this.chip(s)
          }, (s: string) => s)
        }
      }
      .scrollable(ScrollDirection.Horizontal)
      .scrollBar(BarState.Off)
      .width('100%')

      if (this.msg.length > 0) {
        Text(this.msg)
          .fontSize(13)
          .fontColor(Theme.DANGER)
          .width('100%')
      }

      if (this.items.length === 0 && !this.loading) {
        Column({ space: 10 }) {
          Text('这里还没有已过审的学习视频')
            .fontSize(14)
            .fontColor(Theme.TEXT_SUB)
          Text('去「交棒」上传你的学习视频，通过复核后就会出现在这里')
            .fontSize(12)
            .fontColor(Theme.TEXT_FAINT)
            .textAlign(TextAlign.Center)
        }
        .width('100%')
        .padding(24)
        .backgroundColor(Theme.CARD)
        .borderRadius(Theme.RADIUS)
      }

      List({ space: 12 }) {
        ForEach(this.items, (c: ContentInfo) => {
          ListItem() {
            this.card(c)
          }
        }, (c: ContentInfo) => c.id.toString())
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

  @Builder
  card(c: ContentInfo) {
    Row({ space: 12 }) {
      if (this.coverUrl(c).length > 0) {
        Image(this.coverUrl(c))
          .width(88)
          .height(60)
          .borderRadius(Theme.RADIUS_SM)
          .objectFit(ImageFit.Cover)
      } else {
        Column() {
          Text('🎬')
            .fontSize(22)
        }
        .width(88)
        .height(60)
        .backgroundColor('#E8EEF6')
        .borderRadius(Theme.RADIUS_SM)
        .justifyContent(FlexAlign.Center)
      }

      Column({ space: 5 }) {
        Text(c.title)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
        Text((c.subject ? c.subject : '') + (c.knowledge_point ? ' · ' + c.knowledge_point : ''))
          .fontSize(11)
          .fontColor(Theme.TEXT_SUB)
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
        Row({ space: 10 }) {
          Text(Fmt.durationText(c.duration_sec))
            .fontSize(11)
            .fontColor(Theme.TEXT_FAINT)
          Text('👍 ' + (c.helpful ? c.helpful.toString() : '0'))
            .fontSize(11)
            .fontColor(Theme.TEXT_FAINT)
          if (c.owner_name) {
            Text(c.owner_name)
              .fontSize(11)
              .fontColor(Theme.TEXT_FAINT)
          }
        }
        .width('100%')
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .padding(12)
    .backgroundColor(Theme.CARD)
    .borderRadius(Theme.RADIUS)
    .alignItems(VerticalAlign.Top)
  }
}