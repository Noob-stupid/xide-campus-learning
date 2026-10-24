import { webview } from '@kit.ArkWeb';
import { BASE_URL } from '../net/Api';
import { router } from '@kit.ArkUI';

interface ShellParams {
  path?: string;
}

/** Web 兜底页：交棒上传、头像/封面编辑等复杂表单可暂时走网页。 */
@Entry
@Component
struct WebShell {
  controller: webview.WebviewController = new webview.WebviewController();
  @State loading: boolean = true;
  @State errorText: string = '';
  private webUrl: string = BASE_URL;

  aboutToAppear(): void {
    const p = router.getParams() as ShellParams;
    if (p && p.path) {
      this.webUrl = BASE_URL + p.path;
    }
  }

  build() {
    Stack() {
      Web({ src: this.webUrl, controller: this.controller })
        .width('100%')
        .height('100%')
        .domStorageAccess(true)
        .fileAccess(true)
        .geolocationAccess(true)
        .zoomAccess(true)
        .mixedMode(MixedMode.None)
        .onPageBegin(() => {
          this.loading = true;
        })
        .onPageEnd(() => {
          this.loading = false;
        })
        .onErrorReceive((event) => {
          this.loading = false;
          if (event && event.error) {
            this.errorText = '页面加载失败：' + event.error.getErrorInfo();
          }
        })

      if (this.loading) {
        Column() {
          LoadingProgress().width(48).height(48)
          Text('习得加载中…').fontSize(14).fontColor('#FFFFFF').margin({ top: 12 })
        }
        .width('100%')
        .height('100%')
        .justifyContent(FlexAlign.Center)
        .backgroundColor('#0F2A4A')
      }

      if (this.errorText.length > 0) {
        Column() {
          Text(this.errorText).fontSize(16).fontColor('#FFFFFF').textAlign(TextAlign.Center)
          Button('重试')
            .margin({ top: 16 })
            .onClick(() => {
              this.errorText = '';
              this.controller.loadUrl(this.webUrl);
            })
        }
        .width('100%')
        .height('100%')
        .justifyContent(FlexAlign.Center)
        .backgroundColor('#0F2A4A')
        .padding(24)
      }
    }
    .width('100%')
    .height('100%')
  }

  onBackPress(): boolean {
    if (this.controller.accessBackward()) {
      this.controller.backward();
      return true;
    }
    return false;
  }
}
