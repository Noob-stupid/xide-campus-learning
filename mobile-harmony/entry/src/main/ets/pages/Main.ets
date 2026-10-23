import { Theme } from '../common/Theme';
import { HomeView } from '../components/HomeView';
import { SeatsView } from '../components/SeatsView';
import { LearnView } from '../components/LearnView';
import { PoolView } from '../components/PoolView';
import { ProfileView } from '../components/ProfileView';

/** 底部 5 Tab 主界面：今日 / 空间 / 学习 / 接力池 / 我的 */
@Entry
@Component
struct Main {
  @StorageLink('tab') tab: number = 0;

  aboutToAppear(): void {
    if (AppStorage.get<number>('tab') === undefined) {
      AppStorage.setOrCreate('tab', 0);
    }
  }

  @Builder
  bar(icon: string, label: string, idx: number) {
    Column({ space: 2 }) {
      Text(icon)
        .fontSize(19)
        .opacity(this.tab === idx ? 1 : 0.45)
      Text(label)
        .fontSize(11)
        .fontColor(this.tab === idx ? Theme.PRIMARY : Theme.TEXT_SUB)
        .fontWeight(this.tab === idx ? FontWeight.Medium : FontWeight.Normal)
    }
    .width('100%')
    .height(56)
    .justifyContent(FlexAlign.Center)
  }

  build() {
    Tabs({ barPosition: BarPosition.End, index: this.tab }) {
      TabContent() {
        HomeView()
      }
      .tabBar(this.bar('🏠', '今日', 0))

      TabContent() {
        SeatsView()
      }
      .tabBar(this.bar('🪑', '空间', 1))

      TabContent() {
        LearnView()
      }
      .tabBar(this.bar('📖', '学习', 2))

      TabContent() {
        PoolView()
      }
      .tabBar(this.bar('🔁', '接力池', 3))

      TabContent() {
        ProfileView()
      }
      .tabBar(this.bar('👤', '我的', 4))
    }
    .onChange((i: number) => {
      this.tab = i;
    })
    .barHeight(58)
    .scrollable(false)
    .animationDuration(0)
    .width('100%')
    .height('100%')
    .backgroundColor(Theme.BG)
  }
}