let allItems = [];
let currentFilter = "all";
let searchQuery = "";

const CATEGORY_RULES = [
  {
    name: "security",
    pattern: /security|vulnerability|cve|exploit|malware|ransomware|breach|attack|hack|threat|pentest|penetration|metasploit|burp|hack the box|ctf|red team|ペネトレーション|セキュリティ|脆弱性|攻撃/i,
  },
  {
    name: "ai",
    pattern: /\bai\b|artificial intelligence|machine learning|deep learning|gpt|llm|neural|人工知能|機械学習/i,
  },
  {
    name: "tech",
    pattern: /programming|development|code|software|framework|library|api|database|技術|プログラミング|開発/i,
  },
];

function detectCategory(item) {
  const text = ((item.title || "") + " " + (item.title_ja || "") + " " + (item.tags || []).join(" ") + " " + (item.source || "")).toLowerCase();
  const categories = CATEGORY_RULES.filter((rule) => rule.pattern.test(text)).map((rule) => rule.name);
  const uniqueCategories = [...new Set(categories)];
  return uniqueCategories.length > 0 ? uniqueCategories : ["news"];
}

async function fetchData() {
  try {
    const response = await fetch("./data/news.json");
    if (!response.ok) throw new Error("news.json取得失敗");

    const data = await response.json();

    allItems = (data.items || []).map((item) => ({
      ...item,
      categories: detectCategory(item),
      displayTitle: item.title_ja || item.title || "",
      score: item.score || 0,
      link: item.url || item.link || "#",
    }));

    document.getElementById("headerStats").textContent = `総記事数: ${allItems.length} | 最終更新: ${new Date(data.updated_at).toLocaleString("ja-JP")}`;

    renderNews();
  } catch (error) {
    document.getElementById("newsContainer").innerHTML = `<div class="error">
            ❌ データ取得エラー<br>
            ${error.message}<br><br>
            <small>data/news.jsonが存在するか確認してください</small>
          </div>`;
  }
}

function buildBalancedAll(items, limit = 50) {
  const strictCaps = {
    sns: 20,
    jpcert: 15,
    ipa: 15,
    techracho: 15,
  };
  const grouped = new Map();
  for (const item of items) {
    const source = item.source || "unknown";
    if (!grouped.has(source)) grouped.set(source, []);
    grouped.get(source).push(item);
  }
  const sourceOrder = Array.from(grouped.keys());
  const sourceIndex = Object.fromEntries(sourceOrder.map((source) => [source, 0]));

  const selected = [];
  const selectedKeys = new Set();
  const sourceCounts = {};

  let progressed = true;
  while (selected.length < limit && progressed) {
    progressed = false;
    for (const source of sourceOrder) {
      if (selected.length >= limit) break;
      const cap = strictCaps[source] ?? limit;
      if ((sourceCounts[source] || 0) >= cap) continue;

      const sourceItems = grouped.get(source);
      while (sourceIndex[source] < sourceItems.length) {
        const item = sourceItems[sourceIndex[source]++];
        const key = item.link || item.url || item.displayTitle;
        if (!key || selectedKeys.has(key)) continue;
        selected.push(item);
        selectedKeys.add(key);
        sourceCounts[source] = (sourceCounts[source] || 0) + 1;
        progressed = true;
        break;
      }
    }
  }

  if (selected.length < limit) {
    for (const item of items) {
      if (selected.length >= limit) break;
      const key = item.link || item.url || item.displayTitle;
      if (!key || selectedKeys.has(key)) continue;
      selected.push(item);
      selectedKeys.add(key);
    }
  }

  return selected;
}

function renderNews() {
  const container = document.getElementById("newsContainer");
  const topSection = document.getElementById("topSection");

  let filtered = allItems;

  if (currentFilter === "top") {
    topSection.style.display = "block";
    renderTopRanking();
    container.innerHTML = "";
    return;
  } else if (currentFilter === "archive") {
    topSection.style.display = "none";
    renderArchive();
    return;
  } else {
    topSection.style.display = "none";

    if (currentFilter !== "all") {
      filtered = filtered.filter((item) => item.categories.includes(currentFilter));
    }
  }

  if (searchQuery) {
    filtered = filtered.filter((item) => item.title.toLowerCase().includes(searchQuery) || item.displayTitle.toLowerCase().includes(searchQuery) || (item.author && item.author.toLowerCase().includes(searchQuery)));
  }

  if (filtered.length === 0) {
    container.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">🔍</div>
            <div>該当する記事が見つかりませんでした</div>
          </div>
        `;
    return;
  }

  const grid = document.createElement("div");
  grid.className = "news-grid";

  const displayItems = currentFilter === "all" && !searchQuery ? buildBalancedAll(filtered, 50) : filtered.slice(0, 50);

  displayItems.forEach((item) => {
    const card = createNewsCard(item);
    grid.appendChild(card);
  });

  container.innerHTML = "";
  container.appendChild(grid);
}

function createNewsCard(item) {
  const card = document.createElement("div");
  card.className = "news-card";
  card.onclick = () => window.open(item.link, "_blank");

  card.innerHTML = `
        <div class="news-content">
          <div class="news-tags">
            ${item.categories.map((cat) => `<span class="tag ${cat}">${getCategoryLabel(cat)}</span>`).join("")}
          </div>
          <div class="news-title">${item.displayTitle}</div>
          <div class="news-meta">
            <div class="news-source">
              <span>📡</span>
              <span>${item.source}</span>
            </div>
            <div class="news-actions">
              <button class="action-btn" onclick="event.stopPropagation()" title="スコア">
                <span>👍</span>
                <span>${item.score}</span>
              </button>
            </div>
          </div>
        </div>
      `;

  return card;
}

function renderTopRanking() {
  const topList = document.getElementById("topList");
  const rankedByScore = allItems.filter((item) => item.score > 0).sort((a, b) => b.score - a.score);
  const useScoreRanking = rankedByScore.length > 0;
  const topItems = (useScoreRanking
    ? rankedByScore
    : [...allItems].sort((a, b) => {
      const ad = new Date(a.date || 0).getTime();
      const bd = new Date(b.date || 0).getTime();
      return bd - ad;
    })
  ).slice(0, 20);

  if (topItems.length === 0) {
    topList.innerHTML = '<div class="empty-state">表示できる記事がありません</div>';
    return;
  }

  topList.innerHTML = topItems
    .map((item, index) => {
      const rankClass = index === 0 ? "gold" : index === 1 ? "silver" : index === 2 ? "bronze" : "";
      const dateLabel = item.date ? new Date(item.date).toLocaleDateString("ja-JP") : "-";

      return `
          <div class="top-item" onclick="window.open('${item.link}', '_blank')">
            <div class="top-rank ${rankClass}">${index + 1}</div>
            <div class="top-content">
              <div class="top-title">${item.displayTitle}</div>
              <div class="top-meta">
                <span>📡 ${item.source}</span>
                <span class="top-score">${useScoreRanking ? `👍 ${item.score}` : `📅 ${dateLabel}`}</span>
              </div>
            </div>
          </div>
        `;
    })
    .join("");
}

async function renderArchive() {
  const container = document.getElementById("newsContainer");

  try {
    const response = await fetch("./data/archive/index.json");
    if (!response.ok) throw new Error("アーカイブが見つかりません");

    const data = await response.json();

    if (!data.months || data.months.length === 0) {
      container.innerHTML = `
            <div class="empty-state">
              <div class="empty-state-icon">📅</div>
              <div>月次アーカイブはまだありません</div>
            </div>
          `;
      return;
    }

    const section = document.createElement("div");
    section.className = "archive-section";
    section.innerHTML = "<h2>📅 月次アーカイブ</h2>";

    const grid = document.createElement("div");
    grid.className = "archive-grid";

    data.months.forEach((month) => {
      const card = document.createElement("div");
      card.className = "archive-card";
      const htmlFile = month.html_file || `${month.month}.html`;
      card.onclick = () => window.open(`./data/archive/${htmlFile}`, "_blank");

      const summary = month.summary || generateMonthlySummary(month);

      card.innerHTML = `
            <div class="archive-month">${month.month}</div>
            <div class="archive-stats">総記事数: ${month.total_articles || 0}件</div>
            <div class="archive-summary">${summary}</div>
          `;

      grid.appendChild(card);
    });

    section.appendChild(grid);
    container.innerHTML = "";
    container.appendChild(section);
  } catch (error) {
    container.innerHTML = `
          <div class="error">
            ❌ アーカイブ取得エラー<br>
            ${error.message}
          </div>
        `;
  }
}

function generateMonthlySummary(month) {
  if (month.summary) {
    return month.summary;
  }

  const count = month.total_articles || 0;

  if (count === 0) {
    return "記事はありません";
  } else if (count < 50) {
    return `${count}件の記事を収録。セキュリティアップデートや技術トレンドを中心にカバー。`;
  } else if (count < 200) {
    return `${count}件の記事を収録。AI、セキュリティ、開発ツールなど幅広いトピックを網羅。`;
  } else {
    return `${count}件の記事を収録。セキュリティインシデント、AI技術革新、開発トレンドなど充実のラインナップ。`;
  }
}

function getCategoryLabel(category) {
  const labels = {
    security: "セキュリティ",
    ai: "AI",
    tech: "技術",
    news: "ニュース",
  };
  return labels[category] || category;
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    renderNews();
  });
});

let searchTimeout;
document.getElementById("searchInput").addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    searchQuery = e.target.value.toLowerCase();
    renderNews();
  }, 300);
});

fetchData();
