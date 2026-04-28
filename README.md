# 📠 HASAMI-DX：FAX伝票自動デジタル化システム

> 波佐見焼の窯元向け。LINEで伝票を撮って送るだけで、AIが内容を読み取りNotionに自動登録する受注管理システム。

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini-1.5%20Flash-4285F4)](https://ai.google.dev/)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E)](https://railway.app/)

---

## 🎯 解決する課題

長崎県波佐見町の伝統的陶磁器産業「波佐見焼」の窯元では、現在もFAXや手書き伝票による受発注が主流です。担当者が目視で内容を確認し、Excelや台帳に手動で転記するワークフローが続いており、以下の課題が発生しています：

- **1件あたり5〜10分の転記工数**：FAX受信から台帳記入までの作業負担
- **繁忙期の転記ミス**：陶器市（GW期間）など受発注が集中する時期にミスが発生しやすい
- **データのサイロ化**：担当者個人のExcelに閉じ、情報共有・集計が困難

## 💡 ソリューション

> 「伝票の写真を1枚送るだけで、自動でデータベースに登録される」

窯元スタッフは新しいアプリのインストールも操作の習得も不要。**普段使っているLINEで写真を送るだけ**で、AI（Google Gemini）が伝票の内容を読み取り、Notionデータベースに自動登録します。

---

## 🏗️ アーキテクチャ

```
ユーザー（LINE）
    ↓ 画像送信
FastAPI Webhook Server（Railway）
    ↓ 画像バイナリ取得
Google Gemini 1.5 Flash（AI解析）
    ↓ 構造化JSON
Notion API（データベース登録）
    ↓ 完了通知
ユーザー（LINE）
```

### 技術スタック

| 役割 | 技術 |
| --- | --- |
| Webhook受信 | FastAPI（Python）+ uvicorn |
| AIエンジン | Google Gemini 1.5 Flash |
| データベース | Notion API |
| ホスティング | Railway（クラウド常時稼働） |
| バージョン管理 | GitHub |
| 秘密情報管理 | 環境変数（.env / Railway Variables） |

### Notionデータベース設計

固定構造＋柔軟テキスト欄のハイブリッド設計を採用しています。

| プロパティ | 型 | 用途 |
| --- | --- | --- |
| タイトル | title | 「送信元 - 日付」自動生成 |
| 送信元 | text | 取引先名 |
| 日付 | date | 送信日 |
| 品目 | text | 品名・数量・単価（複数行） |
| 合計金額 | number（¥） | 集計・フィルタリング用 |
| 備考 | text | AI注釈・補足 |
| 生データ | text | Gemini出力JSON全文（保険） |
| ステータス | select | 未処理 / 処理中 / 完了 |
| 受信日時 | created_time | 自動 |

「生データ」欄に構造化JSON全文を保存することで、想定外の項目情報が失われない設計としています。

---

## 🚀 セットアップ

### 必要なもの

- Python 3.13以上
- LINE Developersアカウント（Messaging API）
- Google AI Studio APIキー（Gemini）
- Notionワークスペース＋内部インテグレーション

### 1. クローン＆依存インストール

```bash
git clone https://github.com/FORTUNE784/hasami-dx.git
cd hasami-dx
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.template` をコピーして `.env` を作成し、各値を設定してください。

```bash
LINE_CHANNEL_SECRET=your_line_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
GEMINI_API_KEY=your_gemini_api_key
NOTION_API_KEY=your_notion_internal_integration_token
NOTION_DATABASE_ID=your_notion_database_id
```

### 3. Notionデータベースの準備

1. [notion.com/my-integrations](https://www.notion.com/my-integrations) で内部インテグレーションを作成
2. 上記のスキーマに沿ったデータベースを作成
3. データベースの「…」→「接続」→ 作成したインテグレーションを追加
4. データベースIDをURLから取得（`https://notion.so/<workspace>/<DATABASE_ID>?v=...`）

### 4. ローカル起動

```bash
uvicorn main:app --reload
```

### 5. Railwayへのデプロイ（本番）

```bash
git push origin main
```

Railwayと連携済みであれば、push毎に自動デプロイされます。LINE DevelopersのWebhook URLを `https://<your-app>.up.railway.app/webhook` に設定してください。

---

## 📁 プロジェクト構成

```
hasami-dx/
├── main.py                   # FastAPI本体・Webhookハンドラ
├── config.py                 # 環境変数管理（pydantic）
├── notion_schema.py          # Notion登録ロジック
├── requirements.txt          # 依存パッケージ
├── Procfile                  # Railway起動コマンド
├── railway.toml              # Railwayデプロイ設定
├── .env.template             # 環境変数テンプレート
└── .gitignore                # 秘密情報除外
```

---

## 📊 成果（見込み）

- **転記工数**：1件あたり約5〜10分 → 約10秒（写真を撮ってLINEで送るだけ）
- **月額運用コスト**：約700円（Railway $5 / Gemini無料枠 / LINE無料プラン）
- **導入コスト**：窯元スタッフ側ゼロ（既存LINEアカウントから利用可能）

> ※ 上記は設計上の見込み。実運用での実測値は陶器市以降に取得予定。

---

## 🛠️ 設計上の判断記録

### Difyから Pythonへの方針転換

当初はノーコードツール「Dify」でワークフローを構築しようとしましたが、変数参照のUI操作・外部API連携の設定難易度が高く、時間対効果が悪いと判断。Python（FastAPI）による直接実装に切り替えました。GitHub公開によるポートフォリオ価値も考慮した結果です。

### Notionスキーマの設計：固定構造＋生データ欄

「画像ごとにプロパティを動的生成する」アイデアを以下の理由で却下しました：

- 数ヶ月後にプロパティが100個以上に増殖し、データベースが破綻する
- 集計・フィルタリングが不可能になる
- Notionの設計思想（同一構造のデータ蓄積）に反する

代わりに、固定スキーマ＋「生データ」欄に構造化JSON全文を保存するハイブリッド設計を採用しました。想定外の項目があっても情報は失われません。

### Railway採用の理由

- Render無料枠は15分でcold startが発生し、LINE Webhookのタイムアウトリスクあり
- ngrokは PC常時起動が必要で本番運用に不向き
- Railway $5/月で常時稼働＋GitHub連携による自動デプロイを実現

---

## 🔮 今後の展望

- [ ] 複数の伝票パターン（複数品目、FAXかすれ、日付フォーマット違い）でのテスト追加
- [ ] 波佐見陶器まつり前後の窯元への導入提案
- [ ] 導入後の定量データ（削減工数・エラー率）の収集
- [ ] 読み取り精度の継続的改善（プロンプトチューニング）
- [ ] 複数窯元への横展開と運用フィードバック収集

---

## 📄 ライセンス

MIT License

---

## 👤 著者

**FORTUNE784**

長崎県波佐見町の伝統産業「波佐見焼」のDX推進プロジェクト「HASAMI-Next」の一環として開発。

- GitHub: [@FORTUNE784](https://github.com/FORTUNE784)

---

## 🙏 謝辞

- 波佐見焼の窯元の皆様
- Google Gemini APIチーム
- Notion API
- LINE Messaging API
