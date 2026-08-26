# OpenKTV AI 去人聲遷移歷程

## 目標

將目前的 `Spleeter + TensorFlow 2.3` 改為 `ONNX Runtime + MDX-Net`，降低對舊 CPU AVX 指令集的依賴，讓 AMD A8-3870 使用者有機會在本機完成 AI 去人聲。

> 支援條件必須以 AMD A8-3870 實機測試為準。完成打包或成功載入 ONNX Runtime，不代表完整歌曲分離流程已驗證成功。

## 現況基線

- [x] 已確認專案架構與下載、AI 分離、FFmpeg 合成流程
- [x] 已確認 Spleeter 2.0.2 硬性相依 `tensorflow==2.3.0`
- [x] 已確認目前發布包包含 TensorFlow 原生檔案
- [x] 已確認開發機 TensorFlow 2.3.0 可載入
- [x] 已確認使用者 CPU 為 AMD A8-3870，沒有 AVX 指令集
- [x] 已確認安裝 VC++ x64 仍無法解決問題
- [ ] 目前仍保留 Spleeter 流程，尚未開始替換
- [x] 管理頁加入 AI 引擎選擇欄位
- [x] 後端接收並驗證 `ai_engine` 參數
- [x] MDX-Net 未完成前，以停用選項與明確錯誤訊息防止誤用

## 遷移階段

### 1. 技術可行性驗證

- [ ] 確認 Python 3.8 可使用的 ONNX Runtime CPU 版本
- [ ] 確認該 ONNX Runtime 版本在不支援 AVX 的 CPU 上可載入
- [ ] 選定可合法取得且與 MDX-Net 相容的模型
- [ ] 確認模型檔案大小、授權、記憶體需求與下載/離線部署方式
- [ ] 建立獨立測試程式：WAV 輸入，輸出人聲與伴奏 WAV
- [ ] 在開發機以測試音檔驗證輸出品質與處理時間
- [ ] 在 AMD A8-3870 實機驗證 `import onnxruntime` 與完整推論

### 2. 建立 AI 分離抽象層

- [ ] 新增獨立的 AI 分離模組，不讓 `main.py` 直接綁定 Spleeter
- [ ] 定義固定輸出介面：`vocals.wav` 與 `accompaniment.wav`
- [ ] 加入模型、執行環境與輸出檔案的錯誤檢查
- [ ] 保留 Spleeter 作為暫時回退選項
- [ ] 將錯誤記錄改為可辨識的階段與原因

### 3. 整合 KTV 製作流程

- [ ] 將 `process_song` 的步驟 2 改用 MDX-Net 分離器
- [ ] 維持現有下載、檔名處理、FFmpeg L/R 合成與歌單同步行為
- [ ] 確認處理失敗時暫存檔會清理，且不產生半成品歌曲
- [ ] 確認重複歌曲、特殊字元與長歌曲仍可處理
- [ ] 更新管理介面顯示文字與處理進度

### 4. 打包與部署

- [ ] 更新依賴與建置設定，移除不再需要的 TensorFlow/Spleeter 打包內容
- [ ] 將 ONNX Runtime 原生 DLL 與 MDX-Net 模型納入 onedir 發布包
- [ ] 更新 `build_release.ps1` 與 `build_update.ps1`
- [ ] 建立發布前自動檢查：模型存在、runtime 可載入、輸出檔案可產生
- [ ] 以全新資料夾測試完整發布包，不混用舊 `_internal`
- [ ] 更新 README 的需求、安裝、模型與故障排除說明

### 5. 驗收標準

- [ ] AMD A8-3870 可啟動發布版
- [ ] AMD A8-3870 可完成一首短測試音檔的 vocal/accompaniment 分離
- [ ] YouTube 下載後可完成完整四步驟製作
- [ ] 產出的 MP4 可正常播放，且 L/R 原唱與伴奏切換正常
- [ ] 記錄實際處理時間、峰值記憶體與輸出品質
- [ ] 至少使用兩首不同類型歌曲測試
- [ ] 若 MDX-Net 仍不相容，改採區域網路遠端 AI 處理方案

## 決策紀錄

### 2026-08-26

- 目前 TensorFlow 方案在 AMD A8-3870 上因缺少 AVX 而失敗；安裝 VC++ x64 後仍無法解決。
- 不採用直接升級/降級 TensorFlow，因 Spleeter 2.0.2 鎖定 TensorFlow 2.3.0。
- 優先評估 ONNX Runtime + MDX-Net；必須先通過舊 CPU 的獨立推論測試，再整合到主程式。
- 若本機 ONNX Runtime 或模型仍要求 AVX，改用另一台支援 AVX 的電腦提供 AI 分離服務。

## 目前工作

- [ ] 下一步：建立 ONNX Runtime + MDX-Net 的最小可行性測試環境
