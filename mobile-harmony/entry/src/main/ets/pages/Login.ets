import { Api } from '../net/Api';
import { router } from '@kit.ArkUI';
import { Theme } from '../common/Theme';

/** 登录页。演示账号密码：student / reviewer / admin / teacher，密码 123456 */
@Entry
@Component
struct Login {
  @State username: string = 'student';
  @State password: string = '123456';
  @State busy: boolean = false;
  @State error: string = '';

  async doLogin(): Promise<void> {
    if (this.busy) {
      return;
    }
    this.busy = true;
    this.error = '';
    try {
      const r = await Api.login(this.username.trim(), this.password);
      if (r.ok && r.user) {
        AppStorage.setOrCreate('user', r.user);
        router.replaceUrl({ url: 'pages/Main' });
      } else {
        this.error = r.error ? r.error : '登录失败';
      }
    } catch (e) {
      this.error = '网络错误：请确认 BASE_URL 为已部署的 HTTPS 地址';
    } finally {
      this.busy = false;
    }
  }

  build() {
    Column() {
      Column({ space: 8 }) {
        Text('习得')
          .fontSize(36)
          .fontWeight(FontWeight.Bold)
          .fontColor(Theme.WHITE)
        Text('校园学习空间 · AI 创新应用')
          .fontSize(13)
          .fontColor('#B9C7DB')
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
      .margin({ top: 80, bottom: 26 })

      Column({ space: 14 }) {
        Text('登录')
          .fontSize(18)
          .fontWeight(FontWeight.Medium)
          .fontColor(Theme.TEXT)
          .width('100%')

        TextInput({ placeholder: '账号', text: this.username })
          .height(48)
          .borderRadius(Theme.RADIUS_SM)
          .backgroundColor('#F5F7FA')
          .onChange((v: string) => {
            this.username = v;
          })

        TextInput({ placeholder: '密码', text: this.password })
          .type(InputType.Password)
          .height(48)
          .borderRadius(Theme.RADIUS_SM)
          .backgroundColor('#F5F7FA')
          .onChange((v: string) => {
            this.password = v;
          })

        if (this.error.length > 0) {
          Text(this.error)
            .fontSize(13)
            .fontColor(Theme.DANGER)
            .width('100%')
        }

        Button(this.busy ? '登录中…' : '登 录')
          .width('100%')
          .height(46)
          .backgroundColor(Theme.PRIMARY)
          .fontColor(Theme.WHITE)
          .enabled(!this.busy)
          .onClick(() => {
            this.doLogin();
          })

        Text('演示账号：student / reviewer / admin / teacher，密码 123456')
          .fontSize(12)
          .fontColor(Theme.TEXT_FAINT)
          .width('100%')
          .margin({ top: 4 })
      }
      .width('100%')
      .padding(18)
      .backgroundColor(Theme.WHITE)
      .borderRadius(Theme.RADIUS)

      Blank()
    }
    .width('100%')
    .height('100%')
    .padding({ left: 20, right: 20 })
    .backgroundColor(Theme.PRIMARY)
    .alignItems(HorizontalAlign.Start)
  }
}