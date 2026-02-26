# GitHub Copilot Instructions for GalTransl-BGI

## 環境要求

在此專案中執行任何 Python 命令之前，**必須**先啟動 `galtransl` conda 虛擬環境。

### 終端機命令規則

1. **在執行 Python 腳本前，務必先啟動環境：**
   ```bash
   conda activate galtransl
   ```

2. **或使用單行命令格式：**
   ```bash
   conda activate galtransl && python <script.py>
   ```

3. **可用的 Python 腳本：**
   - `extract_bsa.py` - BSA 檔案解包工具
   - `convert_bsg.py` - BSG 圖片轉換工具
   - `export_script.py` - 腳本文本導出工具
   - `import_script.py` - 腳本文本導入工具

### 範例命令

```bash
# 導出遊戲文本
conda activate galtransl && python export_script.py BSA/bsxx.dat -o exported

# 導入翻譯
conda activate galtransl && python import_script.py import BSA/bsxx.dat exported/script.json

# 驗證翻譯進度
conda activate galtransl && python import_script.py validate exported/script.json

# 驗證特定 context 類型
conda activate galtransl && python import_script.py validate exported/script.json -c name

# 匯出未翻譯條目供手動翻譯
conda activate galtransl && python import_script.py validate exported/script.json -c dialog -o untranslated.json

# 解包 BSA 檔案
conda activate galtransl && python extract_bsa.py BSA/*.bsa -o BSA_extracted

# 轉換 BSG 圖片
conda activate galtransl && python convert_bsg.py BSA_extracted/Graphics -o images
```

## 專案資訊

- **專案類型**: Bishop 引擎視覺小說遊戲翻譯工具
- **Python 版本**: 3.11
- **Conda 環境名稱**: `galtransl`

## 檔案格式

- **BSA**: 遊戲資源檔案庫
- **BSG**: 遊戲圖片格式
- **BSXScript 3.1**: 遊戲腳本格式（`bsxx.dat`）
- **UTF-16LE**: 腳本文本編碼

## 注意事項

- 工作目錄: `/raid/home/jimhsieh/GalTransl-BGI`
- 導入工具會自動創建 `.bak` 備份檔案
- 翻譯 JSON 檔案使用 UTF-8 編碼
