// 【‼️ 請將下方網址改成你的 Render 後端網址 ‼️】
// 範例：'https://su-hua-dashboard.onrender.com'
const BACKEND_URL = 'https://su-hua-dashboard.onrender.com';

document.addEventListener('DOMContentLoaded', () => {

  const updateBtn          = document.getElementById('updateBtn');
  const lastUpdateElement  = document.getElementById('lastUpdate');
  const rainList           = document.getElementById('rain-list');
  const radarImage         = document.getElementById('radar-image');
  const rainfallMapImage   = document.getElementById('rainfall-map-image');
  const earthquakeList     = document.getElementById('earthquake-list');
  const roadList           = document.getElementById('road-list');
  const typhoonBox         = document.getElementById('typhoon-box');

  updateBtn.addEventListener('click', () => {
    fetchDataAndUpdateDashboard();
  });

  // ─── 主要資料抓取函式 ───────────────────────────
  async function fetchDataAndUpdateDashboard() {
    lastUpdateElement.textContent = '資料最後更新時間：讀取中…';

    if (!BACKEND_URL || BACKEND_URL === 'YOUR_RENDER_URL_HERE') {
      alert('錯誤：請先在 script.js 中填入後端網址！');
      lastUpdateElement.textContent = '錯誤：後端網址尚未設定';
      return;
    }

    try {
      const res = await fetch(BACKEND_URL + '/api/dashboard-data');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      updateDashboard(data);
    } catch (err) {
      console.error('讀取資料失敗:', err);
      lastUpdateElement.textContent = '資料讀取失敗，請確認後端服務是否正常運作';
    }
  }

  // ─── 圖片載入（加時間戳避免瀏覽器快取舊圖）─────
  function loadImages() {
  const ts = Date.now();

  // 直接從氣象局載入，不經過後端，速度更快也更穩定
  radarImage.src = `https://www.cwa.gov.tw/Data/radar/CV1_3600.png?t=${ts}`;
  rainfallMapImage.src = `https://c1.1968services.tw/map-data/O-A0040-002.jpg?t=${ts}`;

  radarImage.onerror = () => {
    // 第一個來源失敗，換備用雷達圖
    radarImage.onerror = null;
    radarImage.src = `https://www.cwa.gov.tw/Data/radar/CV2_3600.png?t=${ts}`;
    radarImage.onerror = () => { radarImage.alt = '⚠️ 氣象局雷達圖暫時無法載入'; };
  };
  rainfallMapImage.onerror = () => {
    rainfallMapImage.alt = '⚠️ 累積雨量圖暫時無法載入';
  };
}

  // ─── 儀表板更新 ──────────────────────────────────
  function updateDashboard(data) {
    lastUpdateElement.textContent = `資料最後更新時間：${data.lastUpdate}`;
    loadImages();
    renderRain(data.rainInfo || []);
    renderEarthquake(data.earthquakeInfo || []);
    renderRoad(data.roadInfo || {});
    renderTyphoon(data.typhoonInfo);
  }

  // ─── 雨量 ─────────────────────────────────────────
  function renderRain(rainInfo) {
    rainList.innerHTML = '';
    if (!rainInfo.length) {
      rainList.innerHTML = '<li>雨量資料讀取失敗</li>';
      return;
    }
    rainInfo.forEach(item => {
      const li = document.createElement('li');
      let mmText = '', levelText = item.level;

      if (item.mm === 'N/A') {
        mmText = '';
      } else if (parseFloat(item.mm) === 0) {
        mmText = '0 mm';
        levelText = '過去 24 小時無降雨';
      } else {
        mmText = `${item.mm} mm`;
      }

      const timeHtml = item.time ? `<span class="data-time">（${item.time}）</span>` : '';
      let forecastHtml = '';
      if (item.forecast) {
        let fClass = 'forecast-safe';
        if (item.forecast.includes('%') && parseInt(item.forecast) > 50) fClass = 'forecast-warning';
        if (item.forecast.includes('失敗')) fClass = 'forecast-error';
        forecastHtml = `<div class="forecast-line ${fClass}">└── 未來 6 小時：${item.forecast}</div>`;
      }

      li.innerHTML = `<div>${item.location}：<span class="rain-mm ${item.class}">${mmText}</span> ${levelText} ${timeHtml}</div>${forecastHtml}`;
      rainList.appendChild(li);
    });
  }

  // ─── 地震 ─────────────────────────────────────────
  function renderEarthquake(eqInfo) {
    earthquakeList.innerHTML = '';

    if (!eqInfo.length) {
      const li = document.createElement('li');
      li.className = 'eq-none';
      li.textContent = '✅ 過去 72 小時內，宜蘭、花蓮、台東無有感地震（2 級以上）';
      earthquakeList.appendChild(li);
      return;
    }

    eqInfo.forEach(item => {
      const li = document.createElement('li');
      const linkHtml = item.report_url
        ? ` <a href="${item.report_url}" target="_blank" class="detail-link">[詳細報告]</a>`
        : '';

      // 各縣市震度標籤
      const levelBadge = (name, level) => {
        const n = parseInt(level);
        let cls = n >= 5 ? 'eq-level-high' : (n >= 3 ? 'eq-level-mid' : 'eq-level-low');
        return `<span class="eq-badge ${cls}">${name} ${n > 0 ? level + '級' : '—'}</span>`;
      };

      li.innerHTML = `
        <div class="eq-time">${item.time}</div>
        <div class="eq-main">
          震央：${item.location}　
          規模 <strong>M${item.magnitude}</strong>　
          深度 ${item.depth} km
          ${linkHtml}
        </div>
        <div class="eq-levels">
          ${levelBadge('宜蘭縣', item.yilan_level)}
          ${levelBadge('花蓮縣', item.hualien_level)}
          ${levelBadge('台東縣', item.taitung_level)}
        </div>`;
      earthquakeList.appendChild(li);
    });
  }

  // ─── 路況 ─────────────────────────────────────────
  function renderRoad(roadSections) {
    roadList.innerHTML = '';
    const displayOrder = ['蘇澳－南澳', '南澳－和平', '和平－秀林'];
    let total = 0;

    displayOrder.forEach(sname => {
      const incidents = roadSections[sname] || [];
      if (!incidents.length) return;

      total += incidents.length;
      incidents.forEach(item => {
        const li = document.createElement('li');
        const oldTag   = item.is_old_road
          ? '<span class="old-road-tag">（舊蘇花）</span>'
          : '<span class="new-road-tag">（新蘇花）</span>';
        const linkHtml = item.detail_url
          ? ` <a href="${item.detail_url}" target="_blank" class="detail-link">[詳細資訊]</a>`
          : '';

        li.innerHTML = `
          <div>${sname} ${oldTag}：<span class="road-status ${item.class}">${item.status}</span></div>
          <div class="road-desc">${item.desc}</div>
          <div class="data-time">${item.time}${linkHtml}</div>`;
        roadList.appendChild(li);
      });
    });

    // 有「其他蘇花路段」也顯示
    const others = roadSections['其他蘇花路段'] || [];
    if (others.length) {
      total += others.length;
      others.forEach(item => {
        const li = document.createElement('li');
        const linkHtml = item.detail_url
          ? ` <a href="${item.detail_url}" target="_blank" class="detail-link">[詳細資訊]</a>`
          : '';
        li.innerHTML = `
          <div>其他路段：<span class="road-status ${item.class}">${item.status}</span></div>
          <div class="road-desc">${item.desc}</div>
          <div class="data-time">${item.time}${linkHtml}</div>`;
        roadList.appendChild(li);
      });
    }

    if (total === 0) {
      const li = document.createElement('li');
      li.innerHTML = '蘇澳－秀林 全線：<span class="road-status road-green">✅ 目前無異常事件</span>';
      roadList.appendChild(li);
    }
  }

  // ─── 颱風 ─────────────────────────────────────────
  function renderTyphoon(info) {
    if (info) {
      typhoonBox.style.background = '#fff7ed';
      typhoonBox.innerHTML = `
        <div class="typhoon-name">🌀 ${info.name}</div>
        <div>${info.warning_type}｜更新時間：${info.update_time}</div>
        <div>中心位置：${info.location}　最大風速：${info.wind_speed} m/s</div>
        <div class="typhoon-status">${info.status}</div>
        <div><img src="${info.img_url}" alt="颱風路徑圖" width="100%" style="border-radius:8px;margin-top:8px;"></div>`;
    } else {
      typhoonBox.style.background = 'none';
      typhoonBox.innerHTML = '✅ 目前無颱風警報';
    }
  }

  // ─── 頁面載入時立即執行 ───────────────────────────
  fetchDataAndUpdateDashboard();
});
