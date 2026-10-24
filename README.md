# tech-feeds

[技術ニュース集](https://ba230t.github.io/tech-feeds/)。  
`fetch_news.py`で取得し、`gen_archive.py`で月次を作る。

## 構成

```
.github/workflows/update-news.yml
index.html
assets/app.css
assets/app.js
scripts/fetch_news.py
scripts/gen_archive.py
requirements.txt
data/news.json
data/archive/*
```

## ローカル実行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/fetch_news.py
python scripts/gen_archive.py
```
