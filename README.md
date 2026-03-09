# GalTransl-BGI

Bishop 引擎遊戲翻譯工具集，用於解包、轉換和翻譯 Bishop 引擎的視覺小說遊戲資源。

## 環境設置

```bash
# 創建並啟用 conda 虛擬環境
conda create -n galtransl python=3.11 -y
conda activate galtransl
```

> 重要：執行任何 Python 腳本前，請先啟用 `galtransl` 環境，或使用單行命令
> `conda activate galtransl && python <script.py>`。

## 快速開始

```bash
conda activate galtransl && python export_script.py BSA/bsxx.dat -o translation
conda activate galtransl && python import_script.py validate translation/script.json
```

## 工具說明

### 1. BSA 解包工具 (`extract_bsa.py`)

從 BSA 檔案庫中解包所有檔案。

```bash
conda activate galtransl && python extract_bsa.py BSA/*.bsa -o BSA_extracted
```

### 2. BSG 圖片轉換工具 (`convert_bsg.py`)

將 BSG 格式圖片轉換為 PNG 格式。

```bash
conda activate galtransl && python convert_bsg.py BSA_extracted/Graphics -o images_output
```

### 3. 腳本文本導出工具 (`export_script.py`)

從 `bsxx.dat` 導出遊戲文本到 JSON 格式，供翻譯使用。

```bash
# 導出到單一 JSON 檔案
conda activate galtransl && python export_script.py BSA/bsxx.dat -o exported

# 分類導出（按名稱、對話、其他分開）
conda activate galtransl && python export_script.py BSA/bsxx.dat -o exported -s
```

**輸出格式：**
- `script.json` - 包含所有文本條目
- 或分離的 `names.json`、`dialogs.json`、`other.json`

**JSON 結構：**
```json
{
  "info": {
    "magic": "BSXScript 3.1",
    "version": 1024,
    "string_count": 2689
  },
  "strings": [
    {
      "index": 0,
      "offset": 429088,
      "original": "原文文本",
      "translated": "",
      "context": "dialog"
    }
  ]
}
```

### 4. 腳本文本導入工具 (`import_script.py`)

將翻譯後的 JSON 文本導入回 `bsxx.dat`。

**子命令：**

#### `validate` - 驗證翻譯進度並匯出未翻譯文本

```bash
# 驗證翻譯進度（預設顯示未翻譯的對話）
conda activate galtransl && python import_script.py validate translation/script.json

# 指定 context 類型過濾：dialog（預設）、name、other、all
conda activate galtransl && python import_script.py validate translation/script.json -c name
conda activate galtransl && python import_script.py validate translation/script.json -c all

# 將未翻譯的條目匯出為 JSON 檔案，方便手動翻譯
conda activate galtransl && python import_script.py validate translation/script.json -c dialog -o untranslated_dialog.json
conda activate galtransl && python import_script.py validate translation/script.json -c name -o untranslated_names.json
```

選項：
- `-c`, `--context`：要過濾的 context 類型，可選 `dialog`（預設）、`name`、`other`、`all`
- `-o`, `--output`：將未翻譯條目輸出為 JSON 檔案

#### `import` - 導入翻譯

```bash
# 導入翻譯（會自動備份原始檔案）
conda activate galtransl && python import_script.py import BSA/bsxx.dat translation/script.json -o BSA/bsxx_translated.dat

# 不創建備份
conda activate galtransl && python import_script.py import BSA/bsxx.dat translation/script.json --no-backup
```

#### `check` - 檢查翻譯後檔案的結構完整性

比對原始 `bsxx.dat` 與翻譯後的檔案，檢查導入過程中是否存在影響遊戲正常執行的結構性錯誤。

```bash
conda activate galtransl && python import_script.py check BSA/bsxx.dat.bak BSA/bsxx_translated.dat
```

檢查項目：

| 項目 | 說明 |
|------|------|
| Magic & Header | 驗證檔案標識是否一致 |
| 代碼區完整性 | 比對 code 區塊（檔頭定義的字串表之前區域）是否完全相同 |
| Header 偏移量指標 | 驗證 name/dialog index/string 四個表的 offset/size 連續且在有效範圍內 |
| 名稱索引表 | 依 header 計算名稱索引數量，逐一驗證索引是否指向有效字串 |
| 對話索引表 | 依 header 計算對話索引數量，驗證索引是否在有效範圍內並抽樣檢查 |
| 檔案大小 | 檢查大小差異是否在合理範圍內 |

若所有檢查通過，程式回傳 exit code 0；若發現錯誤則回傳 1。

## 翻譯工作流程

1. **解包遊戲資源**
   ```bash
   conda activate galtransl && python extract_bsa.py BSA/*.bsa -o BSA_extracted
   ```

2. **導出文本**
   ```bash
   conda activate galtransl && python export_script.py BSA/bsxx.dat -o translation
   ```

3. **翻譯** - 編輯 `translation/script.json`，在每個條目的 `translated` 欄位填入翻譯文本

4. **驗證翻譯**
   ```bash
   # 查看翻譯進度統計
   conda activate galtransl && python import_script.py validate translation/script.json

   # 匯出未翻譯的對話供手動翻譯
   conda activate galtransl && python import_script.py validate translation/script.json -c dialog -o untranslated_dialog.json

   # 匯出未翻譯的角色名稱
   conda activate galtransl && python import_script.py validate translation/script.json -c name -o untranslated_names.json
   ```

5. **導入翻譯**
   ```bash
   conda activate galtransl && python import_script.py import BSA/bsxx.dat translation/script.json -o BSA/bsxx_translated.dat
   ```

6. **檢查翻譯後的檔案結構**
   ```bash
   conda activate galtransl && python import_script.py check BSA/bsxx.dat.bak BSA/bsxx_translated.dat
   ```

## 支援格式

### BSA 檔案格式
- 簽名: `BSArc`
- 版本: 1-3
- 目錄結構: 層級式

### BSG 圖片格式
- 簽名: `BSS-Graphics`
- 色彩模式: BGRA32, BGR32, Indexed8
- 壓縮: None, RLE, LZ

### BSXScript 3.1 腳本格式
- 簽名: `BSXScript 3.1`
- 文本編碼: UTF-16LE
- 檔案結構：name/dialog 的 index/string table 位置與大小由 header（0x88-0xA4）定義，實作上應以 header 動態讀取，避免硬編碼。

| 區域 | 位置 | 說明 |
|------|------|------|
| Header | 0x0000 - ... | 包含 magic、version、section table 與 0x88-0xA4 表格指標 |
| 代碼區 | ... | 遊戲指令區（導入時應保持 byte-for-byte 不變） |
| Name Index/String Tables | 由 header 指定 | 名稱索引（uint32 字元偏移）與 UTF-16LE 字串表 |
| Dialog Index/String Tables | 由 header 指定 | 對話索引（uint32 字元偏移）與 UTF-16LE 字串表 |

## 文件結構

```
GalTransl-BGI/
├── extract_bsa.py      # BSA 解包工具
├── convert_bsg.py      # BSG 圖片轉換工具
├── export_script.py    # 文本導出工具
├── import_script.py    # 文本導入/驗證/檢查工具
├── check_script.py     # 檔案差異診斷工具 (舊版)
├── doc/                # 教學文件與筆記本
├── BSA/                # 原始遊戲 BSA 檔案
├── BSA_extracted/      # 解包後的檔案
├── exported/           # 導出的翻譯文本
└── README.md           # 本文件
```

## 注意事項

- 導入工具會自動創建 `.bak` 備份檔案
- 翻譯時只需填寫 `translated` 欄位，保持 `original` 和 `offset` 不變
- 建議先在測試環境驗證翻譯效果

## 授權

MIT License
