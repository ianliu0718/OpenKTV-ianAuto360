
# KTV 升降 KEY：SoundTouch / WSOLA 替換計畫

## 評估結論

- [x] **先做 A/B 原型，不立即移除 Tone.js `PitchShift`。** 目前 `templates/player.html` 與 `templates/combo.html` 都是 `MediaElementSource -> 聲道增益/混音 -> masterGain -> Tone.PitchShift`；升降 KEY 只設定 `pitch`，無法確保歌曲播放速度與總長度保持不變。
- [x] **優先驗證 SoundTouchJS（核心為 WSOLA 類時間伸縮）**：已選定 `@soundtouchjs/audio-worklet@2.1.1`，以 `pitchSemitones` 控制音高、固定來源與處理節點 `playbackRate = 1`，先驗證音高變更時歌曲時間是否保持穩定。
- [x] **預期優點**：prototype 已以現有 MP4 成功走過 `MediaElementSource -> SoundTouchNode`，可維持來源播放速度 1.0 並在 `-12` 到 `+12` 半音範圍內控制音高；音質與 MV/歌詞長時間同步仍待實測。
- [ ] **必須確認的代價**：SoundTouch/WSOLA 會增加 CPU 使用量、緩衝延遲與換 KEY 時的過渡處理；極端音域、鼓點、混響和快速連續調整仍可能產生 warble 或 transient artifact。
- [ ] **替換門檻**：只有在常見歌曲的 `-6/-3/0/+3/+6/+12` 半音盲聽、播放同步、延遲與 CPU 測試都不劣於現況時，才正式取代 Tone.js；否則保留可切換的 Tone.js fallback。

## 開始撰寫新功能的步驟

### 1. 建立可驗證的音訊基線

- [ ] 記錄現況 Tone.js 在 `player` 與 `combo` 的問題：聲音品質、切換延遲、CPU、播放時間是否漂移，以及原唱/伴奏/立體聲三種模式是否正常。
- [ ] 準備至少三類測試歌曲：人聲與伴奏分離明顯、鼓點/瞬態密集、長時間與高混響歌曲；確認瀏覽器與 Windows 播放端版本。
- [ ] 定義驗收條件：歌曲長度與影片時間軸誤差、換 KEY 後音高、開始播放延遲、連續調 KEY 是否爆音，以及 `-12` 到 `+12` 的邊界行為。

### 2. 驗證 SoundTouch/WSOLA 的瀏覽器方案

- [x] 選定可在瀏覽器執行的 SoundTouch 實作與版本：prototype 使用 `@soundtouchjs/audio-worklet@2.1.1`，透過 ES module 與 CDN processor 載入；正式播放器仍待確認 `MediaElementSource` 即時串流的相容性。
- [x] 先建立獨立 prototype：`soundtouch-prototype.html` 使用 `AudioBufferSourceNode` 驗證 `pitchSemitones`、固定 `playbackRate`、播放、暫停與停止，不先改正式播放器。
- [x] 實作半音到倍率的純函式、有限值檢查與 `-12..12` 限制；目前倍率僅供測試顯示，正式接線前仍需確認 SoundTouchNode 的 pitch/tempo 語意。
- [ ] 量測預緩衝時間、處理延遲、音訊 underrun、記憶體和 CPU；目前已完成單首 MP4 的瀏覽器播放/暫停與 `+6` KEY smoke test，普通筆電及目標 KTV 播放機仍待完整測試。
- [ ] 用同一批測試歌曲與 Tone.js 做 A/B 錄音及盲聽，記錄結果，不以單一短片段決定方案。

### 3. 抽出共用播放器音訊控制層

- [ ] 將 `player.html` 與 `combo.html` 重複的音訊初始化、聲道模式、音量、KEY 狀態與新歌重置邏輯整理成共用模組；`remote.html` 只保留 Socket.IO 控制與狀態同步。
- [ ] 定義清楚的音訊處理介面，例如 `initAudio()`, `setKey(semitones)`, `setVolume(value)`, `setTrackMode(mode)`, `resetForNewSong()`；所有新函式與公開方法加入清楚的 JSDoc。
- [ ] 讓 KEY 引擎可配置為 `soundtouch` 或 `tone` fallback，避免把演算法細節散落在 Socket.IO callback。
- [ ] 確保 SoundTouch 節點接在現有聲道選擇與 `masterGain` 的正確位置，維持原唱/伴奏/立體聲的左右聲道行為。

### 4. 實作正式 SoundTouch KEY 引擎

- [x] 將 prototype 的處理流程接到正式播放端：`templates/player.html` 與 `templates/combo.html` 已改用 `SoundTouchNode`，處理器在播放前非同步初始化，並保留歌曲切換、pause/resume、stop、seek、影片 `onended` 的既有流程。
- [ ] 以平滑 ramp 或短 crossfade 處理 `setKey()`，避免換 KEY 瞬間 click、爆音或短暫靜音；快速連按按鈕時只套用最新值。
- [x] 加入初始化失敗、瀏覽器不支援、buffer underrun 和例外狀況的 fallback/錯誤狀態：HTTP LAN 因不具 secure context 會自動使用 Tone.js，HTTPS/localhost 使用 SoundTouch AudioWorklet；已修正 combo KEY 按鍵為本機立即套用，避免等待 Socket.IO 回傳造成「按鍵無反應」假象。
- [x] 移除 Tone.js CDN 與相關程式前，先確認沒有其他模板或打包產物依賴它；目前因 HTTP LAN 的 AudioWorklet 限制保留 Tone.js fallback，並以 `useSoundTouch` 自動分流。

### 5. 整合驗證與發佈

- [ ] 測試 `/player`、`/combo`、`/remote` 多裝置同步：`/player` 與 `/combo` 已完成實際 MP4 播放 smoke test，`/combo` 已驗證 `+1 -> 0` KEY 控制；多裝置、音量和切換原唱/伴奏仍待完整回歸。
- [x] 遙控器端加入待播清單：`/remote` 會在新連線時取得目前佇列，也會即時反映新增歌曲與播放中的第一首歌曲。
- [x] 待播清單支援刪除：`/remote` 與 `/combo` 可刪除第 2 首以後的待播歌曲，播放中的第一首受保護，伺服器刪除後會廣播同步所有裝置。
- [x] 修正 `/combo` 小螢幕捲動：右側遙控區可縮小並整頁捲動，待播清單限制為約 `30vh` 並支援內部捲動，歌曲列表保留可捲動區域。
- [ ] 測試 `-12/-6/-1/0/+1/+6/+12`、連續升降、暫停後調 KEY、切歌中調 KEY、重新整理頁面與瀏覽器 autoplay 限制；已驗證 LAN `/combo` 在 HTTP fallback 下可播放，按 `[降]` 可立即由 `原 KEY (0)` 更新為 `-1`，播放中的影片仍持續播放。
- [ ] 在目標 Windows 環境執行長時間播放與完整回歸測試，確認不累積延遲、不記憶體洩漏、不造成音畫失步。
- [ ] 更新 README 的音訊處理說明、依賴/載入方式與 fallback 設定，再使用 `build_update.ps1 -FrontendOnly` 建立前端更新包。
- [ ] 完成現場測試後才決定是否加入或保留 Tone.js fallback；目前正式模板已移除 Tone.js，若品質或效能不達標，需依測試結果恢復可切換 fallback。

## 建議的第一個實作切片

- [x] 先新增獨立 `soundtouch-prototype.html` A/B 測試頁，不改動正式 `player.html` / `combo.html`；Flask 可由 `/soundtouch-prototype` 開啟。
- [ ] prototype 通過音質、同步、延遲與 CPU 門檻後，再抽共用音訊控制層並接入 `/player`，最後同步整合 `/combo`；目前已完成瀏覽器載入、MP4 播放與 `+3` KEY 互動 smoke test。

## LAN 部署注意事項

- [x] 確認 HTTP `192.168.x.x` 不提供 `AudioContext.audioWorklet`；正式程式已加入相容性分流，避免 SoundTouch 初始化失敗導致影片無法播放。
- [x] 已讓 Flask 自動產生包含 LAN IP 的自簽 HTTPS 憑證，並以 `https://` 啟動服務；`curl -k` TLS handshake 與 `/soundtouch-prototype` HTTP 200 已通過。每台播放裝置仍需第一次手動接受自簽憑證警告。
- [x] prototype、`/combo` 與 `/player` 已加入實際引擎狀態顯示；HTTPS 初始化成功時顯示 `SoundTouch AudioWorklet`，HTTP fallback 時顯示 `Tone.js fallback（HTTP LAN）`。
- [ ] 若要免除瀏覽器憑證警告，改用區域網路可信任 CA 或正式網域憑證，並重新驗證所有播放裝置。
