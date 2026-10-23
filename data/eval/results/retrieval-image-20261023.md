# 阶段 7 检索评测结果

- 生成时间：2026-10-23T06:50:42.474072+00:00
- 数据集：`retrieval_cases.jsonl`（sha256 `03978693a19316b8`，143 条）
- 模型：`BAAI/bge-m3`｜维度 1024｜revision `local`｜权重指纹 `468b391066f99bc2703682b65930cc82`
- 检索配置：dense top30 + sparse top30，RRF k=60，最终 4-8 个片段，证据阈值 0.62

| 模式 | 用例 | 行为正确率 | 命中率 | MRR | 片段召回 | 泄漏用例 | 误答 | 误拒 | 平均片段 | 平均耗时(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| hybrid | 143 | 0.972 | 0.8601 | 0.8347 | 0.9021 | 1 | 4 | 0 | 6.68 | 208.2 |
| dense_only_ablation | 143 | 0.972 | 0.8531 | 0.8415 | 0.8951 | 3 | 4 | 0 | 6.64 | 210.38 |

## 双路 vs dense-only：排序差异

- 对比用例：143
- 排序发生变化的用例：129

排序差异说明稀疏支路确实参与了融合；指标相同则说明该数据集上 dense 已足够，不能据此宣称双路提升了召回。

| 用例 | 类别 | 变动位置数 | hybrid 片段数 | dense 片段数 |
|---|---|---|---|---|
| normal-01 | normal | 3 | 8 | 7 |
| normal-02 | normal | 1 | 7 | 8 |
| normal-04 | normal | 2 | 8 | 7 |
| normal-05 | normal | 2 | 7 | 7 |
| normal-06 | normal | 5 | 8 | 8 |
| normal-07 | normal | 4 | 6 | 6 |
| normal-08 | normal | 5 | 8 | 8 |
| no-answer-01 | no_answer | 6 | 7 | 7 |
| no-answer-02 | no_answer | 6 | 7 | 7 |
| no-answer-03 | no_answer | 6 | 7 | 7 |
| expired-01 | expired | 2 | 7 | 7 |
| expired-02 | expired | 3 | 8 | 7 |
| exact-01 | exact_ref | 4 | 7 | 7 |
| exact-02 | exact_ref | 3 | 7 | 7 |
| exact-03 | exact_ref | 4 | 8 | 8 |
| exact-04 | exact_ref | 2 | 6 | 6 |
| exact-05 | exact_ref | 6 | 8 | 8 |
| near-01 | near_dup | 3 | 7 | 8 |
| near-02 | near_dup | 2 | 6 | 6 |
| near-03 | near_dup | 5 | 7 | 8 |
| near-04 | near_dup | 5 | 7 | 7 |
| near-05 | near_dup | 5 | 7 | 6 |
| paraphrase-01 | paraphrase | 7 | 8 | 7 |
| paraphrase-02 | paraphrase | 5 | 7 | 7 |
| paraphrase-03 | paraphrase | 3 | 8 | 7 |
| paraphrase-04 | paraphrase | 4 | 8 | 8 |
| paraphrase-05 | paraphrase | 5 | 7 | 7 |
| r13-01 | exact_fact | 4 | 7 | 7 |
| r13-02 | exact_fact | 4 | 7 | 7 |
| r13-03 | exact_fact | 5 | 6 | 7 |
| r13-04 | exact_fact | 6 | 7 | 7 |
| r13-05 | exact_fact | 3 | 8 | 8 |
| r13-06 | exact_fact | 3 | 7 | 7 |
| r13-07 | exact_fact | 5 | 7 | 7 |
| r13-08 | exact_fact | 7 | 7 | 7 |
| r13-09 | near_dup_hard | 2 | 6 | 6 |
| r13-10 | near_dup_hard | 4 | 6 | 6 |
| r13-11 | near_dup_hard | 2 | 6 | 6 |
| r13-12 | near_dup_hard | 7 | 7 | 7 |
| r13-13 | near_dup_hard | 4 | 7 | 7 |
| r13-14 | near_dup_hard | 5 | 7 | 8 |
| r13-15 | paraphrase_oral | 7 | 7 | 7 |
| r13-16 | paraphrase_oral | 5 | 7 | 7 |
| r13-17 | paraphrase_oral | 6 | 7 | 6 |
| r13-18 | paraphrase_oral | 3 | 7 | 7 |
| r13-19 | paraphrase_oral | 2 | 6 | 6 |
| r13-20 | paraphrase_oral | 6 | 8 | 8 |
| r13-21 | region_sg | 2 | 6 | 6 |
| r13-22 | region_sg | 2 | 6 | 6 |
| r13-23 | region_sg | 6 | 6 | 6 |
| r13-24 | no_answer_v2 | 5 | 7 | 8 |
| r13-25 | no_answer_v2 | 3 | 7 | 7 |
| r13-26 | no_answer_v2 | 6 | 6 | 7 |
| x2-normal-01 | normal | 3 | 7 | 7 |
| x2-normal-02 | normal | 5 | 7 | 7 |
| x2-normal-03 | normal | 4 | 8 | 7 |
| x2-normal-04 | normal | 3 | 7 | 7 |
| x2-normal-05 | normal | 6 | 7 | 7 |
| x2-normal-06 | normal | 3 | 7 | 7 |
| x2-normal-07 | normal | 4 | 7 | 7 |
| x2-normal-08 | normal | 6 | 8 | 8 |
| x2-normal-09 | normal | 4 | 8 | 8 |
| x2-normal-10 | normal | 5 | 8 | 8 |
| x2-normal-11 | normal | 5 | 7 | 8 |
| x2-normal-12 | normal | 4 | 8 | 7 |
| x2-normal-13 | normal | 5 | 7 | 7 |
| x2-exact-01 | exact_fact | 3 | 7 | 7 |
| x2-exact-02 | exact_fact | 4 | 7 | 7 |
| x2-exact-03 | exact_fact | 5 | 8 | 7 |
| x2-exact-04 | exact_fact | 6 | 7 | 7 |
| x2-exact-05 | exact_fact | 6 | 7 | 7 |
| x2-exact-06 | exact_fact | 4 | 7 | 7 |
| x2-exact-07 | exact_fact | 3 | 7 | 7 |
| x2-exact-08 | exact_fact | 3 | 6 | 6 |
| x2-exact-09 | exact_fact | 5 | 6 | 6 |
| x2-exact-10 | exact_fact | 2 | 7 | 7 |
| x2-ver-01 | expired | 2 | 8 | 8 |
| x2-ver-02 | expired | 5 | 8 | 8 |
| x2-ver-03 | expired | 5 | 7 | 7 |
| x2-ver-04 | expired | 4 | 7 | 7 |
| x2-ver-05 | expired | 4 | 7 | 7 |
| x2-ver-06 | expired | 3 | 7 | 7 |
| x2-ver-07 | expired | 6 | 7 | 8 |
| x2-ver-08 | expired | 5 | 8 | 7 |
| x2-ver-10 | expired | 4 | 8 | 8 |
| x2-ver-11 | expired | 3 | 7 | 7 |
| x2-ver-12 | expired | 7 | 7 | 7 |
| x2-ver-13 | expired | 4 | 8 | 7 |
| x2-ver-14 | expired | 5 | 7 | 7 |
| x2-ver-15 | expired | 4 | 7 | 7 |
| x2-ver-16 | expired | 4 | 7 | 7 |
| x2-ver-19 | expired | 6 | 7 | 8 |
| x2-ver-20 | expired | 5 | 8 | 7 |
| x2-ver-21 | expired | 6 | 8 | 8 |
| x2-ver-22 | expired | 3 | 8 | 7 |
| x2-ver-23 | expired | 3 | 7 | 7 |
| x2-ver-24 | expired | 4 | 7 | 7 |
| x2-ver-25 | expired | 4 | 7 | 7 |
| x2-ver-26 | expired | 4 | 7 | 7 |
| x2-ver-27 | expired | 5 | 8 | 8 |
| x2-ver-28 | expired | 5 | 8 | 7 |
| x2-ver-29 | expired | 6 | 8 | 8 |
| x2-ver-30 | expired | 3 | 8 | 7 |
| x2-ver-31 | expired | 3 | 7 | 7 |
| x2-ver-32 | expired | 5 | 7 | 7 |
| x2-ver-33 | expired | 4 | 8 | 8 |
| x2-ver-34 | expired | 6 | 8 | 8 |
| x2-ver-35 | expired | 5 | 7 | 7 |
| x2-near-01 | near_dup_hard | 6 | 7 | 7 |
| x2-near-02 | near_dup_hard | 5 | 7 | 7 |
| x2-near-03 | near_dup | 2 | 7 | 8 |
| x2-near-04 | near_dup_hard | 4 | 7 | 7 |
| x2-near-05 | near_dup | 5 | 7 | 7 |
| x2-near-06 | near_dup | 6 | 7 | 7 |
| x2-near-07 | near_dup_hard | 1 | 6 | 6 |
| x2-near-08 | near_dup | 5 | 7 | 7 |
| x2-near-09 | near_dup | 3 | 6 | 6 |
| x2-near-10 | near_dup | 3 | 7 | 7 |
| x2-noans-01 | no_answer | 6 | 7 | 7 |
| x2-noans-02 | no_answer | 7 | 7 | 8 |
| x2-noans-03 | no_answer | 5 | 7 | 7 |
| x2-noans-04 | no_answer | 6 | 8 | 7 |
| x2-noans-05 | no_answer | 7 | 7 | 7 |
| x2-noans-06 | no_answer | 7 | 7 | 7 |
| x2-noans-07 | no_answer | 5 | 7 | 7 |
| x2-noans-08 | no_answer | 5 | 6 | 7 |
| image-01 | image | 6 | 7 | 7 |
| image-02 | image | 4 | 7 | 7 |
| image-03 | image | 5 | 8 | 7 |


## 分类结果

### hybrid

| 类别 | 用例 | 行为正确率 | 命中率 | MRR | 误答 | 误拒 |
|---|---|---|---|---|---|---|
| conflict | 4 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| cross_shop | 6 | 1.0 | 0.0 | 0.0 | 0 | 0 |
| exact_fact | 18 | 1.0 | 1.0 | 0.9185 | 0 | 0 |
| exact_ref | 5 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| expired | 37 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| image | 3 | 1.0 | 1.0 | 0.8333 | 0 | 0 |
| near_dup | 11 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| near_dup_hard | 10 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| no_answer | 11 | 0.6364 | 0.0 | 0.0 | 4 | 0 |
| no_answer_v2 | 3 | 1.0 | 0.0 | 0.0 | 0 | 0 |
| normal | 21 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| paraphrase | 5 | 1.0 | 1.0 | 0.7667 | 0 | 0 |
| paraphrase_oral | 6 | 1.0 | 1.0 | 0.9167 | 0 | 0 |
| region_sg | 3 | 1.0 | 1.0 | 1.0 | 0 | 0 |

### dense_only_ablation

| 类别 | 用例 | 行为正确率 | 命中率 | MRR | 误答 | 误拒 |
|---|---|---|---|---|---|---|
| conflict | 4 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| cross_shop | 6 | 1.0 | 0.0 | 0.0 | 0 | 0 |
| exact_fact | 18 | 1.0 | 0.9444 | 0.9444 | 0 | 0 |
| exact_ref | 5 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| expired | 37 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| image | 3 | 1.0 | 1.0 | 0.7778 | 0 | 0 |
| near_dup | 11 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| near_dup_hard | 10 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| no_answer | 11 | 0.6364 | 0.0 | 0.0 | 4 | 0 |
| no_answer_v2 | 3 | 1.0 | 0.0 | 0.0 | 0 | 0 |
| normal | 21 | 1.0 | 1.0 | 1.0 | 0 | 0 |
| paraphrase | 5 | 1.0 | 1.0 | 0.9 | 0 | 0 |
| paraphrase_oral | 6 | 1.0 | 1.0 | 0.9167 | 0 | 0 |
| region_sg | 3 | 1.0 | 1.0 | 1.0 | 0 | 0 |

