# Terra Reader

アークナイツ（日本語版）のシナリオを、スマホ縦持ちでタップ送りしながら読む個人用の静的 Web アプリ。

- 本文・立ち絵・背景・スチルは、読むたびに GitHub 上の公開データから取得します。このリポジトリにはコードと目次データだけを置いています。
- 端末に保存されるのは、既読位置と設定（ドクター名・文字サイズ）だけです。

## 取得元

| 種類 | 場所 |
|---|---|
| 本文 | `ArknightsAssets/ArknightsGamedata` の `jp/gamedata/story/` |
| 立ち絵・背景・スチル | `ArknightsAssets/ArknightsAssets2` cn ブランチの `assets/dyn/avg/` |
| 画像の縮小 | wsrv.nl（設定で無効化できます） |

## ファイル

| ファイル | 役割 |
|---|---|
| `index.html` / `app.css` / `app.js` | 目次とプレイヤー |
| `parser.js` | シナリオ台本（`[name="…"]`、`[charslot(…)]` 等）を「1タップ＝1手」の列に変換 |
| `data/index.json` | 目次。`story_review_table.json` から生成 |
| `data/sprites.json` | 台本の立ち絵名 → 画像パス |
| `data/bgm.json` | BGM の変数名 → 曲名 |

## データの更新

新章・新イベントが追加されたら `data/` の3ファイルを作り直します（生成スクリプトは `tools/` 参照）。本文と画像は常に最新の取得元を参照するため、更新作業は目次だけです。

## ローカルで動かす

```
python -m http.server 8765
```

ブラウザで `http://127.0.0.1:8765/` を開きます。`file://` では動きません（fetch を使うため）。
