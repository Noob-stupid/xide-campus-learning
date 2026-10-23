import { Api, BASE_URL } from '../net/Api';
import { Theme } from '../common/Theme';
import { Fmt } from '../common/Format';
import { UserInfo, StudySession, ContentInfo, RelayPush } from '../model/Types';
import { router } from '@kit.ArkUI';

/** 我的：资料、数据栏、编辑、退出 */
@Component
export struct ProfileView {
  @State user: UserInfo | null = null;
  @State stats: Record<string, number> = {};
  @State sessions: StudySession[] = [];
  @State contents: ContentInfo[] = [];
  @State pushes: RelayPush[] = [];
  @State editing: boolean = false;
  @State eName: string = '';
  @State eCollege: string = '';
  @State eSign: string = '';
  @State eInterest: string = '';
  @State busy: boolean = false;
  @State msg: string = '';

  aboutToAppear(): void {
    this.load();
  }

  async load(): Promise<void> {
    try {
      const r = await Api.profile();
      if (r.ok && r.user) {
        this.user = r.user;
        this.stats = r.stats ? r.stats : {};
        this.sessions = r.sessions ? r.sessions : [];
        this.contents = r.contents ? r.contents : [];
        this.pushes = r.pushes ? r.pushes : [];
        AppStorage.setOrCreate('user', r.user);
      }
    } catch (e) {
      this.msg = '加载失败，请重试';
    }
  }

  openEdit(): void {
    if (!this.user) {
      return;
    }
    const u = this.user as UserInfo;
    this.eName = u.name;
    this.eCollege = u.college ? u.college : '';
    this.eSign = u.signature ? u.signature : '';
    this.eInterest = u.interests ? u.interests : '';
    this.editing = true;
  }

  async saveEdit(): Promise<void> {
    if (this.busy) {
      return;
    }
    this.busy = true;
    try {
      const r = await Api.profileUpdate(this.eName, this.eCollege, this.eSign, this.eInterest);
      if (r.ok) {
        this.editing = false;
        this.msg = '资料已保存';
        await this.load();
      } else {
        this.msg = r.error ? r.error : '保存失败';
      }
    } catch (e) {
      this.msg = '保存失败，请重试';
    } finally {
      this.busy = false;
    }
  }

  async logout(): Promise<void> {
    try {
      await Api.logout();
    } catch (e) {
    }
    await Api.clearSession();
    AppStorage.setOrCreate('user', null);
    router.replaceUrl({ url: 'pages/Login' });
  }

  avatarUrl(): string {
    if (this.user && this.user.avatar_url && this.user.avatar_url.length > 0) {
      return BASE_URL + this.user.avatar_url;
    }
    return '';
  }

  statVal(k: string): string {
    const v = this.stats[k];
    return v === undefined ? '0' : v.toString();
  }

  @Builder
  statCell(label: string, value: string) {
    Column({ space: 3 }) {
      Text(value)
        .fontSize(17)
        .fontWeight(FontWeight.Bold)
        .fontColor(Theme.PRIMARY)
      Text(label)
        .fontSize(11)
        .fontColor(Theme.TEXT_SUB)
    }
    .layoutWeight(1)
  }

  build() {
    Stack() {
      Scroll() {
        Column({ space: 12 }) {
          // 头部
          Column({ space: 10 }) {
            Row({ space: 12 }) {
              if (this.avatarUrl().length > 0) {
                Image(this.avatarUrl())
                  .width(60)
                  .height(60)
                  .borderRadius(30)
                  .objectFit(ImageFit.Cover)
              } else {
                Column() {
                  Text(this.user ? this.user.name.substring(0, 1) : '?')
                    .fontSize(24)
                    .fontColor(Theme.WHITE)
                }
                .width(60)
                .height(60)
                .borderRadius(30)
                .backgroundColor('#2A4A6E')
                .justifyContent(FlexAlign.Center)
              }
              Column({ space: 4 }) {
                Text(this.user ? this.user.name : '未登录')
                  .fontSize(18)
                  .fontWeight(FontWeight.Bold)
                  .fontColor(Theme.WHITE)
                Text(this.user && this.user.college ? this.user.college : '未填写学院')
                  .fontSize(12)
                  .fontColor('#B9C7DB')
              }
              .alignItems(HorizontalAlign.Start)
              .layoutWeight(1)
              Text('编辑')
                .fontSize(13)
                .fontColor(Theme.WHITE)
                .padding({ left: 12, right: 12, top: 6, bottom: 6 })
                .borderRadius(14)
                .backgroundColor('#2A4A6E')
                .onClick(() => {
                  this.openEdit();
                })
            }
            .width('100%')

            if (this.user && this.user.signature && this.user.signature.length > 0) {
              Text(this.user.signature)
                .fontSize(12)
                .fontColor('#D5DEEA')
                .width('100%')
            }
            if (this.user && this.user.interests && this.user.interests.length > 0) {
              Text('兴趣：' + this.user.interests)
                .fontSize(11)
                .fontColor('#9FB4CC')
                .width('100%')
            }
          }
          .width('100%')
          .padding(16)
          .backgroundColor(Theme.PRIMARY)
          .borderRadius(Theme.RADIUS)
          .alignItems(HorizontalAlign.Start)

          if (this.msg.length > 0) {
            Text(this.msg)
              .fontSize(13)
              .fontColor(Theme.ACCENT)
              .width('100%')
          }

          // 数据栏
          Row() {
            this.statCell('学习场次', this.statVal('sessions'))
            this.statCell('专注分钟', this.statVal('minutes'))
            this.statCell('交棒', this.statVal('contents'))
            this.statCell('接棒', this.statVal('relays'))
            this.statCell('有帮助率', this.statVal('helpful_rate') + '%')
          }
          .width('100%')
          .padding(14)
          .backgroundColor(Theme.CARD)
          .borderRadius(Theme.RADIUS)

          // 学习轨迹
          if (this.sessions.length > 0) {
            Text('最近学习轨迹')
              .fontSize(15)
              .fontWeight(FontWeight.Medium)
              .fontColor(Theme.TEXT)
              .width('100%')
              .margin({ top: 4 })
            ForEach(this.sessions.slice(0, 8), (s: StudySession) => {
              Row() {
                Column({ space: 3 }) {
                  Text((s.subject ? s.subject : '自主学习') + ' · ' + (s.seat_code ? s.seat_code : ''))
                    .fontSize(13)
                    .fontColor(Theme.TEXT)
                  Text(Fmt.channelText(s.started_at))
                    .fontSize(11)
                    .fontColor(Theme.TEXT_FAINT)
                }
                .alignItems(HorizontalAlign.Start)
                .layoutWeight(1)
                Text(Fmt.minutesText(s.duration_min))
                  .fontSize(13)
                  .fontColor(Theme.ACCENT)
              }
              .width('100%')
              .padding(12)
              .backgroundColor(Theme.CARD)
              .borderRadius(Theme.RADIUS_SM)
            }, (s: StudySession) => s.id.toString())
          }

          Button('退出登录')
            .width('100%')
            .height(44)
            .backgroundColor('#FBE9EA')
            .fontColor(Theme.DANGER)
            .margin({ top: 8 })
            .onClick(() => {
              this.logout();
            })

          Blank().height(20)
        }
        .width('100%')
        .padding(14)
      }
      .scrollBar(BarState.Off)
      .width('100%')
      .height('100%')

      // 编辑弹层
      if (this.editing) {
        Column() {
          Column({ space: 10 }) {
            Text('编辑资料')
              .fontSize(16)
              .fontWeight(FontWeight.Medium)
              .fontColor(Theme.TEXT)
              .width('100%')
            TextInput({ placeholder: '昵称', text: this.eName })
              .height(44)
              .backgroundColor('#F5F7FA')
              .borderRadius(Theme.RADIUS_SM)
              .onChange((v: string) => {
                this.eName = v;
              })
            TextInput({ placeholder: '学院', text: this.eCollege })
              .height(44)
              .backgroundColor('#F5F7FA')
              .borderRadius(Theme.RADIUS_SM)
              .onChange((v: string) => {
                this.eCollege = v;
              })
            TextInput({ placeholder: '学习签名', text: this.eSign })
              .height(44)
              .backgroundColor('#F5F7FA')
              .borderRadius(Theme.RADIUS_SM)
              .onChange((v: string) => {
                this.eSign = v;
              })
            TextInput({ placeholder: '兴趣方向', text: this.eInterest })
              .height(44)
              .backgroundColor('#F5F7FA')
              .borderRadius(Theme.RADIUS_SM)
              .onChange((v: string) => {
                this.eInterest = v;
              })
            Row({ space: 10 }) {
              Button('保存')
                .layoutWeight(1)
                .height(44)
                .backgroundColor(Theme.PRIMARY)
                .fontColor(Theme.WHITE)
                .enabled(!this.busy)
                .onClick(() => {
                  this.saveEdit();
                })
              Button('取消')
                .width(80)
                .height(44)
                .backgroundColor('#EDF1F7')
                .fontColor(Theme.TEXT_SUB)
                .onClick(() => {
                  this.editing = false;
                })
            }
            .width('100%')
          }
          .width('100%')
          .padding(18)
          .backgroundColor(Theme.CARD)
          .borderRadius(Theme.RADIUS)
          .margin({ left: 20, right: 20 })
          .alignItems(HorizontalAlign.Start)
        }
        .width('100%')
        .height('100%')
        .justifyContent(FlexAlign.Center)
        .backgroundColor('rgba(0,0,0,0.4)')
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Theme.BG)
  }
}