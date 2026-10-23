import { webview } from '@kit.ArkWeb';

/**
 * Web 兜底入口（可选）。
 * 原生版全部功能已用 ArkTS 实现；本页仅用于快速对照 Web 版或降级。
 * 需要在下面填部署好的 HTTPS 地址。
 */
@Entry
@Component
struct WebShell {
  controller: webview.WebviewController = new webview.WebviewController();
  @State loading: boolean = true;
  @State errorText: string = '';

  // TODO: 部署 HTTPS 后填写习得公网地址
  private readonly webUrl: string = 'https://xide.example.com';

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
            this.errorText = '页面加载失败：' + event.error.errorInfo;
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
          Text(this.errorText)
            .fontSize(16)
            .fontColor('#FFFFFF')
            .textAlign(TextAlign.Center)
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