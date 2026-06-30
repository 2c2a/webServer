# 13 - Git 工作流

## 分支模型

```
main          # 生产分支
├── feat/*    # 功能分支
├── hotfix/*  # 紧急修复
└── fix/*     # 普通 bug 修复
```

## 工作流

```bash
# 新功能
git checkout -b feat/my-feature
# 开发...
git add ...
git commit -m "feat: 添加批量主机操作"
git push -u origin feat/my-feature
# PR → 合并 → 删除分支
git branch -d feat/my-feature
git push origin --delete feat/my-feature
```

## 提交规范

```
<type>: <描述>

[可选正文]
```

| Type | 用途 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | bug 修复 |
| `refactor` | 重构 |
| `docs` | 文档 |
| `test` | 测试 |
| `chore` | 构建/工具/依赖 |

描述用中文，不超过 72 字符。

## 禁止

1. 禁止 force push 到 main/master
2. 禁止合并后保留 feat/* 和 hotfix/* 分支
3. 禁止提交 `.env`、密钥、`__pycache__`、`staticfiles/`
4. 禁止未经用户同意提交

## 提交前检查

```bash
ruff check app/
ruff format app/
git status
```