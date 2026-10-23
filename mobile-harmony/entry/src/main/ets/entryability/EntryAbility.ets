import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';
import { Api } from '../net/Api';

const TAG: string = 'XideEntryAbility';

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    hilog.info(0x0000, TAG, 'onCreate');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    // 必须先读完持久化 Cookie，再打开 Index；否则 Index 会把已登录用户误判成未登录。
    Api.init(this.context).then(() => {
      windowStage.loadContent('pages/Index', (err) => {
        if (err.code) {
          hilog.error(0x0000, TAG, 'loadContent failed: %{public}s', JSON.stringify(err));
          return;
        }
        hilog.info(0x0000, TAG, 'loadContent succeeded, hasCookie=%{public}s', Api.hasCookie().toString());
      });
    });
  }
}
