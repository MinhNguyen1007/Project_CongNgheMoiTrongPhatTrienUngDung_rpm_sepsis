# Kaggle CatBoost training — Phase 2

CatBoost GPU training trên Kaggle để tạo model thứ hai cho ensemble.

## Prerequisites (local)

Đã chạy xong Phase 1 local:

```bash
python ml/src/preprocess.py --data-dir data/raw --out-dir data/processed
python ml/src/build_features.py --input-dir data/processed --out-dir data/features
python ml/src/relabel.py --input-dir data/features --out-dir data/features_relabeled --late-cutoff 3 --splits train
```

Kết quả: `data/features_relabeled/{train,val,test}.parquet` (mỗi file 100–500MB).

## Bước trên Kaggle

### 1. Upload dataset

- Zip thư mục `data/features_relabeled/` → upload làm **Kaggle Dataset**
- Tên dataset gợi ý: `sepsis-features-relabeled`
- Type: **Private** (không public dataset PhysioNet đã xử lý)

### 2. Tạo notebook

- New Notebook → Accelerator = **GPU T4 x2** (hoặc P100)
- Settings → Internet = **On** (để pip install nếu cần; CatBoost có sẵn)
- Add Data → attach dataset `sepsis-features-relabeled`

### 3. Paste code

Paste toàn bộ nội dung [train_catboost_kaggle.py](train_catboost_kaggle.py) vào một cell. Run All.

Thời gian chạy ước tính: 15–30 phút (tùy số iterations hội tụ).

### 4. Download artifacts

Từ `/kaggle/working/` download về máy local:
- `catboost_model.cbm`
- `val_proba.parquet`
- `test_proba.parquet`
- `best_params.json`
- `test_metrics.json`
- `threshold_grid.csv`

Lưu vào `ml/kaggle/output/` trong repo local.

## Bước tiếp theo (Phase 3 — local)

1. Chạy LightGBM local với relabeled data + warmup grid:
   ```bash
   python ml/src/train_lgbm.py \
       --features-dir data/features_relabeled \
       --experiment sepsis-lgbm-relabeled \
       --register
   ```
2. Dump LGBM val/test probas (sẽ tạo script `dump_probas.py` ở Phase 3).
3. Ensemble với `ml/src/ensemble.py` — logistic meta-learner trên OOF.

## Ghi chú

- **KHÔNG relabel test split** — utility_score chỉ match PhysioNet ground truth nếu test labels nguyên bản.
- `scale_pos_weight=10` cố định cho cả LGBM và CatBoost để probas comparable khi ensemble.
- Nếu Kaggle timeout: giảm `iterations=3000` hoặc `depth=7`.
- Feature set phải match LGBM — script tự detect từ parquet columns (sorted), nên cần cùng file input.
