# padmapper

XInput 対応のゲームコントローラーの入力を、キーボード・マウスの操作に変換する Windows 用の常駐ツールです。
前面にあるアプリに応じてプロファイルを自動で切り替えるので、デスクトップではマウス代わりに、エミュレーターでは一部のボタンだけ、といった使い分けができます。

- Python の標準ライブラリだけで動きます。追加のパッケージやドライバのインストールは不要です。
- タスクトレイに常駐し、設定画面からボタンの割り当てや感度を調整できます。変更はその場で反映されます。

## 主な機能

- ボタンへのキー（同時押しを含む）、マウスボタン、ホイールの割り当て。押し続けたときの連続入力
- スティックによるカーソル移動・スクロール・方向キー入力。速さ、デッドゾーン、感度カーブ、軸固定を調整可能
- 前面のアプリ（実行ファイル名やフォルダ）に応じたプロファイルの自動切り替えと、プロファイルの継承
- レイヤー（「LT を押している間だけ別の割り当て」や、押すたびに切り替わる割り当て）
- コントローラーの同時押しによる、変換の一時停止と再開

## 動作環境

- Windows 10 / 11
- Python 3.11 以上（設定ファイルの読み込みに標準ライブラリの `tomllib` を使います）
- XInput 対応のコントローラー（Xbox 360 / One / Series のコントローラーと、その互換品）
- 設定画面の表示に Microsoft Edge か Google Chrome（どちらもない場合は既定のブラウザで開きます）

## 導入手順

1. **Python をインストールします。**
   [python.org](https://www.python.org/downloads/windows/) から 3.11 以上をインストールします。
   インストーラーの既定のまま「py launcher」を含めてインストールすると、`.pyw` ファイルをダブルクリックで実行できるようになります。

2. **このリポジトリを取得します。**

   ```
   git clone <このリポジトリの URL>
   ```

3. **起動します。**
   `padmapper.pyw` をダブルクリックします。コンソールウィンドウは出ずに、タスクトレイにコントローラーのアイコンが表示されます。
   初回起動時は、`examples/` にあるサンプルから全体設定とプロファイル（desktop / passthrough）が作られます。

4. **設定画面を開きます。**
   トレイアイコンをクリックすると、設定画面が専用のウィンドウで開きます。

### 動作確認だけをしたい場合

入力を送らずに、送る予定の内容だけを表示するモードがあります。

```
python -m padmapper --dry-run
```

コントローラーのボタンを押すと、`[dry-run] mouse left down` のように表示されます。Ctrl+C で終了します。

### ログイン時に自動で起動する場合（任意）

`Win + R` で `shell:startup` を開き、`padmapper.pyw` へのショートカットを置きます。

## 使い方

| 操作 | 方法 |
|---|---|
| 設定画面を開く | トレイアイコンを左クリック（起動中にもう一度 `padmapper.pyw` を開いても同じ） |
| 変換の一時停止 / 再開 | Back + Start を 1 秒長押し、トレイの右クリックメニュー、または設定画面右上のスイッチ |
| プロファイルを固定する | トレイの右クリック →「プロファイルを固定」、または設定画面の「このプロファイルで試す」 |
| 終了 | トレイの右クリック →「終了」 |

- 変換が有効なときはトレイアイコンが青、無効なときは灰色になります。
- **設定画面が前面にある間は、変換を自動で止めます。** コントローラーを押しても入力は送られず、画面上の図が光るだけです。割り当てを試すときは、試したいアプリを前面にしてください。
- 二重に起動すると入力が二重に送られるため、多重起動はできないようにしています。

### 設定画面

| タブ・場所 | できること |
|---|---|
| ボタン | コントローラーの図か一覧でボタンを選び、動作を割り当てる。キーはキーボードで押して記録できる |
| スティック・感度 | スティックの使い方と感度の調整。反応カーブとスティックの位置がリアルタイムで表示される |
| 対象アプリ・基本設定 | 自動で切り替える対象のアプリ（起動中のアプリから選べる）、継承元、細かい入力設定 |
| レイヤー | ボタン・スティックのタブ上部で切り替え・追加 |
| 全体設定 | 既定のプロファイル、一時停止の同時押し、カーソルの動かし方、読み取り頻度 |
| ログ | 動作の記録 |

## プロファイル

プロファイルは `profiles/` フォルダに 1 ファイル 1 プロファイル（TOML 形式）で保存されます。ファイル名がプロファイル名です。
通常は設定画面で編集しますが、ファイルを直接編集することもできます。その場合は padmapper を起動し直すと反映されます。

- **base**（`profiles/base.toml`）: 全プロファイル共通の設定です。他のプロファイルは `inherit = "base"` でこれを引き継ぎます。
- **desktop**（サンプル）: デスクトップ操作用です。どのアプリにも当てはまらないときに使われます。
- **passthrough**（サンプル）: 何も送らないプロファイルです。コントローラーに対応したゲームを対象アプリに登録して使います。

`profiles/` のうち git で管理しているのは `base.toml` だけです。各自で作ったプロファイルは、各自の環境に合わせたものとして管理対象外にしています。

### 切り替えの仕組み

前面のアプリが、プロファイルの `match` に書いたパターンに当てはまると、そのプロファイルに切り替わります。

- `/` を含まないパターンは、実行ファイル名と照合します（例: `game.exe`）。
- `/` を含むパターンは、フルパスと照合します（例: `D:/Games/*`）。
- `*` は任意の文字列です。大文字と小文字は区別しません。
- 実行ファイル名での一致が、パスでの一致より優先されます。どれにも当てはまらなければ、既定のプロファイルが使われます。

### ファイルの書き方

```toml
inherit = "base"                     # 継承元。書いた項目だけが上書きされる
description = "説明"
match = ["game.exe", "D:/Games/*"]   # 対象アプリ

[settings]
trigger_threshold = 0.3              # LT/RT を押したとみなす押し込み量 (0〜1)
repeat_delay = 0.4                   # 連続入力が始まるまでの秒数
repeat_rate = 20                     # 連続入力の回数 / 秒
scroll_step = 30                     # スクロールを送る単位 (120 = ホイール 1 目盛り)

[sticks.left]                        # left / right
mode = "mouse"                       # mouse / scroll / buttons / none
speed = 1400                         # mouse: ピクセル/秒、scroll: 目盛り/秒
deadzone = 0.15                      # 反応しない範囲 (0〜0.9)
curve = 2.0                          # 大きいほど、少し倒したときに細かく動く
threshold = 0.5                      # buttons モードで押したとみなす倒し具合
invert_y = false                     # 上下を反転する
axis_lock = false                    # 縦横のうち強く倒したほうだけを使う

[buttons]
A = "key:enter"                      # キー
B = "key:ctrl+shift+s"               # 同時押し
X = "mouse:left"                     # left / right / middle / x1 / x2
Y = "wheel:up"                       # up / down / left / right
UP = { do = "key:up", repeat = true }  # 押し続けると連続入力
LT = "layer:fn"                      # 押している間だけレイヤー fn を有効にする
LS = "layer_toggle:touch"            # 押すたびにレイヤー touch を切り替える
GUIDE = "profile:desktop"            # プロファイルを固定する (profile:auto で自動に戻す)
RB = "none"                          # 継承した割り当てを打ち消す

[layers.fn.buttons]                  # レイヤー中だけの割り当て。書いていないボタンは通常の割り当てのまま
A = "key:ctrl+c"

[layers.fn.sticks.left]              # レイヤー中だけのスティック設定
speed = 350
```

- **ボタン名**: `A B X Y LB RB LT RT BACK START GUIDE LS RS UP DOWN LEFT RIGHT`。LS / RS はスティックの押し込みです。
  スティックを `mode = "buttons"` にすると、`LS_UP LS_DOWN LS_LEFT LS_RIGHT`（右は `RS_...`）も使えます。
- **キー名**: `a`〜`z`、`0`〜`9`、`f1`〜`f24`、`enter esc tab space backspace delete insert home end pageup pagedown`、
  `up down left right shift ctrl alt win apps capslock printscreen`、`numpad0`〜`numpad9`、
  `volume_up volume_down volume_mute media_play_pause media_next media_prev`、`comma period minus slash` など。
  キーボード配列によって刻印が異なる記号キーは、`oem_1` などの名前か、`0xBA` のような仮想キーコードで指定します。

全体設定の項目は `examples/config.toml` を参照してください。

## コマンドライン

| コマンド | 内容 |
|---|---|
| `pythonw -m padmapper --tray` | タスクトレイに常駐する（`padmapper.pyw` と同じ） |
| `python -m padmapper` | コンソールで起動する。ログと設定画面の URL を表示する（`padmapper.bat` と同じ） |
| `python -m padmapper --check` | 設定を検証して一覧を表示する（入力は送らない） |
| `python -m padmapper --dry-run` | 入力を送らず、送る予定の内容を表示する |
| `python -m padmapper --profile NAME` | 指定したプロファイルに固定して起動する |
| `python -m padmapper --open` | 起動と同時に設定画面を開く |

## 注意事項

- 入力は Windows の `SendInput` で送ります（AutoHotkey などと同じ仕組み）。コントローラー自体の入力は変えないので、ゲームやエミュレーターには、これまでどおりコントローラーの入力も届きます。
- **ゲームから見たコントローラーのボタンを入れ替えることはできません**（例: B を押すとゲームに A として届く）。これには仮想コントローラーのドライバが必要です。エミュレーターやゲーム内のボタン設定、または Steam Input を使ってください。
- 管理者権限で動いているアプリ（タスクマネージャーなど）が前面にあると、Windows の仕組み上、入力が届きません。
- オンラインゲームでは、passthrough プロファイル（何も送らない）を使うか、padmapper を終了することを推奨します。
- 設定画面は、自分の PC からの接続（127.0.0.1）だけを受け付け、起動ごとのランダムな鍵で認証します。
- 設定画面のアイコンは CDN（Lucide）から読み込み、ハッシュ値（SRI）で内容を固定しています。オフラインではアイコンが表示されませんが、操作はできます。
- 設定画面から保存すると、TOML ファイル内のコメントは消えます。起動後に初めてファイルを書き換えるときは、変更前の内容を自動で控えとして残します。

## 開発

```
padmapper/          本体
├─ engine.py        コントローラーの状態をキー・マウス操作に変換する
├─ profiles.py      プロファイルと全体設定の読み込み・検証
├─ runtime.py       入力処理のループと、設定画面から操作するための共有状態
├─ server.py        設定画面用のローカル HTTP サーバー
├─ tray.py          タスクトレイのアイコン (Win32 API)
├─ uiwindow.py      設定画面のウィンドウ (Edge / Chrome のアプリモード)
├─ xinput.py / output.py / foreground.py / keys.py / tomlwriter.py
└─ web/             設定画面 (HTML / CSS / JavaScript)
profiles/base.toml  共通設定
examples/           初回起動時にコピーされるサンプル
tests/              テスト (tests/fixtures/ にテスト用のプロファイル)
tools/              補助ツール
```

```
python -m unittest discover -s tests -t .   # テスト
python tools/xinput_monitor.py              # コントローラーの入力を表示するだけのモニター
python tools/make_icons.py                  # トレイ・設定画面のアイコンを作り直す
```
