import { Api } from '../net/Api';
import { router } from '@kit.ArkUI';
import { Theme } from '../common/Theme';

/**
 * 入口页：判断会话（持久化 Cookie），已登录进主界面，否则去登录。
 */
@Entry
@Component
struct Index {
  @State tip: string = '正在进入习得…';

  aboutToAppear(): void {
    this.boot();
  }

  async boot(): Promise<void> {
    if (Api.hasCookie()) {
      try {
        const r = await Api.me();
        if (r.ok && r.user) {
          AppStorage.setOrCreate('user', r.user);
          router.replaceUrl({ url: 'pages/Main' });
          return;
        }
      } catch (e) {
        this.tip = '会话校验失败，请重新登录';
      }
    }
    router.replaceUrl({ url: 'pages/Login' });
  }

  build() {
    Stack() {
      Column({ space: 10 }) {
        Text('习得')
          .fontSize(42)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.WHITE)
        Text('从落座到学会 · 离座不放学')
          .fontSize(14)
          .fontColor('#B9C7DB')
      }
      .width('100%')
      .height('100%')
      .justifyContent(FlexAlign.Center)

      Column({ space: 10 }) {
        LoadingProgress()
          .width(26)
          .height(26)
          .color('#8FB3DE')
        Text(this.tip)
          .fontSize(12)
          .fontColor('#8FB3DE')
      }
      .offset({ y: 130 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Theme.PRIMARY)
  }
}