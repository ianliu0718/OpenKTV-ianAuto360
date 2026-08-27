
# 🎤 ianAutoKTV 智慧開源 KTV 系統

ianAutoKTV 是一個基於 Python 與 Web 技術打造的區域網路 KTV 系統。只需輸入 YouTube 網址，系統便會自動下載影片，並利用 AI 模型（Spleeter）將「原唱」與「伴奏」音軌分離，最後透過網頁介面提供專業的 KTV 點歌與播放體驗。

無論是用電視大螢幕播放、手機掃碼遙控，還是用筆電單機歡唱，ianAutoKTV 都能完美支援！

---

## ✨ 核心特色

* **🤖 AI 智慧去人聲**：內建 Spleeter 引擎，一鍵將 YouTube 影片轉換為高水準的 KTV 伴唱帶。
* **📱 手機掃碼遙控器**：無需安裝 App，手機掃描 QR Code 即可化身點歌機，支援搜尋、切歌、音量控制。
* **🎛️ 即時原唱/伴奏與升降 KEY**：透過 Web Audio API，在播放中切換左聲道（原唱）、右聲道（伴奏），並依瀏覽器環境使用 SoundTouch AudioWorklet 或 HTTP LAN 相容的 Tone.js fallback。
* **📺 多螢幕聯動支援**：
    * `播放端`：適合放在客廳電視或第二螢幕全螢幕顯示。
    * `遙控端`：適合多支手機同時連線點歌。
    * `一體機`：適合單台電腦或平板，左半邊看 MV、右半邊點歌。
* **📦 綠色免安裝架構**：支援 PyInstaller 打包，可製作成隨身碟帶著走的免安裝版（Portable）。

---

## 🚀 系統架構與運作原理

1.  **下載階段**：使用 `yt-dlp` 優先下載 H.264/AVC、最高 1080p 的 YouTube 影音，降低舊型電腦以 CPU 軟解 AV1 或 4K 影片造成的播放負擔。
2.  **處理階段**：透過 FFmpeg 將音訊轉出，交由 AI 模型 `spleeter:2stems` 進行人聲與樂器分離。
3.  **合成階段**：利用 FFmpeg 將原唱（左聲道）、伴奏（右聲道）與原畫質影像重新封裝為 `.mp4`。
4.  **播放階段**：Flask + SocketIO 建立的輕量級伺服器，負責串流影片並同步所有連線裝置的指令。

---

## 📂 檔案目錄結構要求 (打包 EXE 後)

如果你是直接下載編譯好的 Windows `.exe` 版本，請確保你的資料夾結構如下，系統才能正常運作：

```text
ianAutoKTV/
 │
 ├── ianAutoKTV_Server.exe    # KTV 伺服器主程式
 ├── yt-dlp.exe               # 影音下載核心
 │
 ├── ffmpeg/                  # FFmpeg 工具包
 │   └── bin/
 │       └── ffmpeg.exe
 │
 ├── templates/               # 前端網頁介面 (必須與 exe 放在同層)
 │   ├── player.html
 │   ├── remote.html
 │   ├── admin.html
 │   └── combo.html
 │
 └── pretrained_models/       # AI 去人聲模型 (離線大腦，第一次執行免等待下載)
     └── 2stems/
         ├── checkpoint
         ├── model.data-00000-of-00001
         ├── model.index
         └── model.meta
```

---

## 🛠️ 開發與本地執行 (適合開發者)

## 📦 Windows 發佈與更新

首次安裝請使用完整的 `dist\ianAutoKTV_Server\` 資料夾，並雙擊其中的 `ianAutoKTV_Server.exe`。不要使用 `dist` 根目錄的單獨 exe。

建立完整主程式包：

```powershell
cd "D:\Buff\Cursor資料夾\OpenKTV-ianAuto360"
.\build_release.ps1
```

建立更新包：

```powershell
.\build_update.ps1
```

如果這次只修改 `templates` 內的網頁檔案，使用純前端更新模式，可避免重新打包與下載大型 `_internal`：

```powershell
.\build_update.ps1 -FrontendOnly
```

純前端更新包只包含 `templates` 與 `VERSION.txt`，不包含 EXE、TensorFlow `_internal`、FFmpeg、模型或 `yt-dlp.exe`。如果修改了 `main.py`、spec、執行環境或任何需要重新打包的內容，仍必須使用一般的 `.\build_update.ps1` 完整更新模式。

更新包會包含新的 `ianAutoKTV_Server.exe`、相容的 `_internal`、`templates`、官方獨立版 `yt-dlp.exe` 與 `VERSION.txt`。請先關閉程式，再將更新包內的全部內容覆蓋到原安裝資料夾；不要只替換 exe。`_internal` 含 TensorFlow 原生 DLL，必須與 exe 來自同一次建置，否則可能出現 TensorFlow DLL 初始化錯誤。

完整更新模式會重新建立並攜帶與 EXE 同一次建置產生的 `_internal`，以避免 TensorFlow 原生 DLL 與 EXE 版本不一致。若只修改網頁模板，請使用 `-FrontendOnly` 純前端更新模式；此模式不會更新 EXE 或 `_internal`。使用者原有的 `ffmpeg`、`pretrained_models`、`ktv_songs` 與 `yt-dlp.exe` 不需替換。

### 1. 環境需求
* Python 3.8 64 位元（Spleeter 2.0.2 搭配 TensorFlow 2.3.0）
* 系統需已安裝 [FFmpeg](https://ffmpeg.org/) 並加入環境變數，或將其放置於專案目錄下。

### 2. 安裝依賴套件
打開終端機，執行以下指令安裝必要套件：
```bash
python -m pip install flask flask-socketio flask-cors spleeter yt-dlp
```

### 3. 啟動伺服器
請在專案資料夾開啟 PowerShell，先啟用虛擬環境：
```powershell
cd "D:\Buff\Cursor資料夾\OpenKTV-ianAuto360"
.\.venv\Scripts\Activate.ps1
```

看到命令列前方出現 `(.venv)` 後，再執行：
```bash
python main.py
```
若不想啟用虛擬環境，也可以直接執行：
```powershell
& "D:\Buff\Cursor資料夾\OpenKTV-ianAuto360\.venv\Scripts\python.exe" "D:\Buff\Cursor資料夾\OpenKTV-ianAuto360\main.py"
```
啟動後，本機將會彈出「伺服器狀態監控器」，並顯示可供連線的 HTTPS 區域網路網址（例如 `https://192.168.1.X:5000/...`）。第一次在每台裝置開啟時，瀏覽器會顯示自簽憑證警告，請選擇進階後繼續前往；接受後才能啟用 SoundTouch AudioWorklet。

---

## 🌐 介面導覽

* **/player**：播放器端。請在客廳電視或外接螢幕的瀏覽器開啟，雙擊即可進入全螢幕。
* **/remote**：遙控器端。請用手機瀏覽器開啟，負責點歌、控制音量、切換原唱/伴奏。
* **/admin**：管理後台。負責貼上 YouTube 網址來製作新歌，並提供系統底層日誌監控。
* **/combo**：雙合一控制台。適合使用單台寬螢幕電腦遊玩，同時整合播放與控制介面。
* **/soundtouch-prototype**：SoundTouch/WSOLA 音訊處理驗證頁，供測試音高、播放同步與瀏覽器相容性。

### 字幕流程

後台的「新增 KTV 歌曲」表單可選擇 `.srt`、`.lrc` 或 `.vtt` 字幕檔，也可在進階文字框直接貼上這三種格式；系統會依檔案副檔名或文字內容自動判斷格式，並在歌曲製作完成後轉換字幕，以歌曲 basename 儲存為同名 `.vtt`。系統日誌下方另設有預設收合的進階「既有歌曲歌詞轉檔」卡片，使用 `.mp4` 檔案選擇器指定既有歌曲，字幕輸出會儲存在歌曲相同位置並覆寫同名 VTT。`/player` 與 `/combo` 使用 HTML5 `<track>` 顯示字幕，`/remote` 與 `/combo` 的「播放中」區域固定提供字幕開關，因此歌曲清單捲動後仍可操作目前歌曲的字幕。

前端模板由 Flask/Jinja 渲染；內嵌 JavaScript 的 JSDoc 型別請避免使用未跳脫的 `{{...}}` 物件型別寫法，以免被誤判為 Jinja 表達式而造成頁面 500 錯誤。

### 為什麼以 VTT 作為儲存與播放格式

SRT 適合人工製作與交換，LRC 適合歌詞同步，VTT 則是 HTML5 `<track>` 的瀏覽器原生格式。統一儲存為 VTT 可以直接交給 `<track>`，不必在每台播放裝置重複轉換，也能使用 WebVTT 的語言、標籤與顯示設定；因此系統接受三種輸入格式，但在伺服器端統一轉成 VTT。這不是說 SRT 或 LRC 不好，而是 VTT 更符合本系統的瀏覽器播放管線。

### 播放效能與舊型電腦

播放端會經過 Chrome 與 Web Audio 音訊分流；在 AMD A8-3870 這類不具 AV1 硬體解碼的舊型平台，4K AV1 或高解析度 AV1 歌曲可能由 CPU 軟體解碼而造成 LAG。系統下載新歌時會優先選擇 H.264/AVC、最高 1080p，以提高硬體解碼機會；既有的 AV1/4K 歌曲仍需使用 FFmpeg 轉成 H.264/1080p 後再播放，避免在瀏覽器播放時即時轉檔。

管理端系統日誌下方的「進階」卡片現在分成兩個獨立且預設收合的功能：既有歌曲歌詞轉檔，以及既有影片效能最佳化。影片功能可直接選擇既有 MP4，上傳後轉成 H.264、最高 1080p，成功後取代 `ktv_songs` 中的同名檔案；歌詞與影片轉檔互不共用輸入欄位。

若不使用管理端 UI，也可以用腳本最佳化單首既有歌曲（會在成功後取代原 MP4，音訊左右聲道會保留）：

```powershell
.\optimize_existing_video.ps1 -InputFile ".\ktv_songs\我甘願重新愛過-洋蔥 Feat.狗柏.mp4"
```

這個最佳化腳本是伺服器外的維護工具，不會在播放時執行；完整主程式包與一般更新包都會附帶此腳本。若只新增或修改此腳本，既有安裝不需要重新打包 EXE；若修改 `main.py` 的下載策略，則既有安裝仍需使用一般 `build_update.ps1` 更新包。

---

## ⚠️ 注意事項

* **版權聲明**：本專案僅供程式交流與個人家庭娛樂使用，請勿將下載之版權影音用於任何商業行為。
* **硬體需求**：AI 去人聲（Spleeter）會消耗一定的 CPU/記憶體資源，處理一首 4 分鐘的歌曲約需 1~3 分鐘不等，請耐心等候。
* **升降 KEY**：播放服務現在以自簽 HTTPS 啟動，播放端使用 SoundTouch AudioWorklet。每台裝置第一次連線需先接受憑證警告；若仍使用舊的 `http://192.168.x.x` 網址，瀏覽器會無法啟用 AudioWorklet。
* `yt-dlp.exe` 必須使用官方獨立執行檔，不要使用 `.venv\Scripts\yt-dlp.exe` 這類可能綁定舊 Python 路徑的 launcher，否則下載歌曲時會回報 Code 1。
* 程式啟動時不會載入 TensorFlow；只有開始下載並處理歌曲時才會載入 Spleeter。若處理歌曲時仍出現 TensorFlow DLL 錯誤，請確認使用完整主程式包，且不要只替換 exe。
* 若啟動時出現 `Failed to load the native Tensorflow runtime`，請使用同一次建置產生的完整主程式包與更新包，不要只替換 exe。
* 若啟動時出現 `Invalid async_mode specified`，請重新執行 `build_release.ps1` 與 `build_update.ps1`，使用新產生的完整資料夾；打包設定已固定使用 `threading` 並納入 Engine.IO driver。
* 若下載成功、只有「AI 去人聲」出現 `DLL 初始化例行程序失敗`，表示程式已啟動，問題通常在使用者電腦的 TensorFlow 執行環境。請先安裝 Microsoft Visual C++ 2015-2022 Redistributable x64，確認 Windows 為 64 位元且 CPU 支援 AVX，再重新測試。若仍失敗，請提供使用者電腦的 CPU 型號與 Windows 版本。
